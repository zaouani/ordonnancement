import heapq
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from ..models import Simulation, Evenement, TaskAssignment, Operator, Task

class SimulationEngine:
    
    @staticmethod
    @transaction.atomic
    def demarrer_simulation(config):
        """
        Initialise une nouvelle simulation à partir d'une configuration
        Args:
            config: {
                'operateurs': [{'id': str, 'learning_params': {'LC': float, 'FC': float}}],
                'taches': [{'id': str, 'product_id': str, 'temps_standard': int}],
                'machines': [{'id': str, 'taches_compatibles': [str]}],
                'produits': [{'id': str, 'cr': float}],
                'duree_max': int (minutes)
            }
        Returns:
            Simulation: Instance du modèle Simulation créée
        """
        # 1. Création de la simulation
        simulation = Simulation.objects.create(
            date_debut=timezone.now(),
            temps_max=config.get('duree_max', 1440),  # Default 24h
            statut='initialisee'
        )
        
        # 2. Création des événements initiaux
        for tache_config in config['taches']:
            if not tache_config.get('precedence'):
                Evenement.objects.create(
                    simulation=simulation,
                    type='DEBUT_TACHE_DISPONIBLE',
                    tache_id=tache_config['id'],
                    temps_planifie=timezone.now()
                )
        
        # 3. Journalisation
        simulation.logs.create(
            message=f"Simulation démarrée avec {len(config['taches'])} tâches initiales",
            timestamp=timezone.now()
        )
        
        return simulation

    @staticmethod
    @transaction.atomic
    def avancer_temps(simulation, minutes):
        """
        Fait avancer l'état de la simulation d'un nombre donné de minutes
        Args:
            simulation: Instance du modèle Simulation
            minutes: Durée à simuler (en minutes)
        Returns:
            list: Événements traités durant cette période
        """
        temps_fin = simulation.temps_actuel + timedelta(minutes=minutes)
        evenements_traites = []
        
        # Récupère les événements dans l'ordre chronologique
        evenements = list(simulation.evenement_set.filter(
            temps_planifie__lte=temps_fin,
            traite=False
        ).order_by('temps_planifie'))
        
        for evenement in evenements:
            if evenement.temps_planifie > temps_fin:
                break
                
            resultat = SimulationEngine.traiter_evenement(evenement)
            evenement.traite = True
            evenement.save()
            
            evenements_traites.append({
                'evenement': evenement,
                'resultat': resultat
            })
            
            # Mise à jour du temps actuel
            simulation.temps_actuel = evenement.temps_planifie
            simulation.save()
        
        return evenements_traites

    @staticmethod
    def traiter_evenement(evenement):
        """
        Traite un événement spécifique et déclenche les actions appropriées
        Args:
            evenement: Instance du modèle Evenement
        Returns:
            dict: Résultats du traitement
        """
        from .scheduler import Ordonnanceur  # Import local pour éviter circularité
        
        resultat = {'status': 'success'}
        
        try:
            if evenement.type == 'DEBUT_TACHE':
                # 1. Récupérer l'assignation concernée
                assignment = TaskAssignment.objects.get(
                    task_id=evenement.tache_id,
                    operator_id=evenement.operateur_id
                )
                
                # 2. Mettre à jour l'état
                assignment.est_en_cours = True
                assignment.save()
                
                # 3. Planifier l'événement de fin
                Evenement.objects.create(
                    simulation=evenement.simulation,
                    type='FIN_TACHE',
                    tache_id=evenement.tache_id,
                    operateur_id=evenement.operateur_id,
                    temps_planifie=evenement.temps_planifie + timedelta(
                        minutes=assignment.temps_estime
                    )
                )
                
                resultat['details'] = f"Tâche {evenement.tache_id} démarrée"
            
            elif evenement.type == 'FIN_TACHE':
                # 1. Marquer la tâche comme terminée
                assignment = TaskAssignment.objects.get(
                    task_id=evenement.tache_id,
                    operator_id=evenement.operateur_id
                )
                assignment.est_terminee = True
                assignment.save()
                
                # 2. Vérifier les tâches suivantes
                task = Task.objects.get(id=evenement.tache_id)
                for next_task in task.next_tasks.all():
                    if next_task.est_pret_pour_assignation():
                        Evenement.objects.create(
                            simulation=evenement.simulation,
                            type='TACHE_DISPONIBLE',
                            tache_id=next_task.id,
                            temps_planifie=evenement.temps_planifie
                        )
                
                resultat['details'] = f"Tâche {evenement.tache_id} terminée"
            
            elif evenement.type == 'TACHE_DISPONIBLE':
                # 1. Trouver un opérateur disponible
                operateur = Ordonnanceur.choisir_operateur(evenement.tache_id)
                if operateur:
                    # 2. Affecter la tâche
                    assignment = Ordonnanceur.affecter_tache(
                        operateur,
                        evenement.tache_id,
                        evenement.simulation
                    )
                    
                    # 3. Planifier le début
                    Evenement.objects.create(
                        simulation=evenement.simulation,
                        type='DEBUT_TACHE',
                        tache_id=evenement.tache_id,
                        operateur_id=operateur.id,
                        temps_planifie=evenement.temps_planifie
                    )
                    
                    resultat['assignment'] = assignment.id
                else:
                    resultat['status'] = 'no_operator'
                    resultat['details'] = "Aucun opérateur disponible"
            
            # Journalisation
            evenement.simulation.logs.create(
                message=f"Événement {evenement.type} traité: {resultat.get('details', '')}",
                timestamp=timezone.now()
            )
            
        except Exception as e:
            resultat['status'] = 'error'
            resultat['error'] = str(e)
            evenement.simulation.logs.create(
                message=f"Erreur traitement événement: {str(e)}",
                timestamp=timezone.now(),
                is_error=True
            )
        
        return resultat
    
    