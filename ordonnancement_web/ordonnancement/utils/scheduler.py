from django.utils import timezone
from django.db.models import Q
from ..models import Operator, Task, Machine, Simulation
import numpy as np

class Ordonnanceur:
    
    @staticmethod
    def choisir_tache(operateur, simulation):
        """
        Sélectionne la tâche optimale selon 4 critères pondérés :
        1. Coût de sous-performance (40%)
        2. Performance historique (20%)
        3. Équité entre opérateurs (20%)
        4. Impact sur le makespan (20%)
        """
        taches_disponibles = Ordonnanceur.taches_disponibles_pour_operateur(operateur, simulation)
        taches_bloquees = Ordonnanceur.taches_non_disponibles(simulation)
        
        scores = []
        
        # Évaluation des tâches disponibles
        for tache in taches_disponibles:
            score = Ordonnanceur.calculer_score(operateur, tache, simulation, 0)
            scores.append((score, tache, 0))  # (score, tâche, temps_attente)
        
        # Évaluation des tâches bloquées
        for tache_data in taches_bloquees:
            score = Ordonnanceur.calculer_score(
                operateur, 
                tache_data['tache'], 
                simulation,
                tache_data['temps_restant']
            )
            scores.append((score, tache_data['tache'], tache_data['temps_restant']))
        
        if not scores:
            return None
            
        # Sélection de la tâche avec le score maximal (et temps d'attente minimal en cas d'égalité)
        meilleure_tache = max(scores, key=lambda x: (x[0], -x[2]))[1]
        return meilleure_tache

    @staticmethod
    def affecter_tache(operateur, tache, simulation):
        """Gère l'assignation complète d'une tâche avec suivi temporel"""
        from ..models import TaskAssignment  # Import local pour éviter circularité
        
        if not tache or tache.quantite_restante <= 0:
            return False

        # Calcul du temps d'exécution ajusté par la performance
        temps_execution = tache.temps_standard / operateur.performance_set.get(task=tache).valeur
        
        # Création de l'assignation
        assignment = TaskAssignment.objects.create(
            operator=operateur,
            task=tache,
            machine=tache.machine_requise,
            debut=timezone.now(),
            fin=timezone.now() + timezone.timedelta(minutes=temps_execution),
            temps_reel=temps_execution
        )
        
        # Mise à jour des quantités
        tache.quantite_restante = 0
        tache.save()
        
        # Journalisation
        simulation.logs.create(
            type='AFFECTATION',
            details=f"{operateur.id} → {tache.id}",
            temps=simulation.temps_actuel
        )
        
        return assignment

    @staticmethod
    def calculer_score(operateur, tache, simulation, temps_attente):
        """Calcule un score composite normalisé [0-1]"""
        # Coefficients de pondération
        poids = {
            'cout': 0.4,
            'performance': 0.2,
            'equite': 0.2,
            'makespan': 0.2
        }
        
        # Calcul des scores partiels
        cout = Ordonnanceur._calculer_score_cout(operateur, tache)
        performance = Ordonnanceur._calculer_score_performance(operateur, tache)
        equite = Ordonnanceur._calculer_score_equite()
        makespan = Ordonnanceur._calculer_score_makespan(simulation, tache)
        
        # Combinaison pondérée
        score_total = (
            poids['cout'] * cout +
            poids['performance'] * performance +
            poids['equite'] * equite +
            poids['makespan'] * makespan -
            (temps_attente / 1440)  # Pénalité d'attente (normalisée sur 1 jour)
        )
        
        return max(0, min(1, score_total))  # Bornage

    @staticmethod
    def taches_disponibles_pour_operateur(operateur, simulation):
        """Retourne les tâches éligibles selon 3 critères :
        1. L'opérateur a les compétences nécessaires
        2. Les précédences sont respectées
        3. La machine requise est libre
        """
        return Task.objects.filter(
            Q(operator__id=operateur.id) &  # L'opérateur est qualifié
            Q(precedence__isnull=True) |  # Pas de précédence
            Q(precedence__in=simulation.tasks_terminees.all()),  # Ou précédence terminée
            quantite_restante__gt=0,
            machine_requise__tache_actuelle__isnull=True  # Machine libre
        ).distinct()

    @staticmethod
    def taches_non_disponibles(simulation):
        """Identifie les tâches bloquées avec leur temps d'attente estimé"""
        taches_bloquees = []
        
        for tache in Task.objects.filter(quantite_restante__gt=0):
            # Vérification machine occupée
            if tache.machine_requise.tache_actuelle:
                temps_restant = (
                    tache.machine_requise.tache_actuelle.fin - 
                    timezone.now()
                ).total_seconds() / 60
                
                taches_bloquees.append({
                    'tache': tache,
                    'raison': 'machine_occupée',
                    'temps_restant': max(0, temps_restant)
                })
            
            # Vérification précédence non terminée
            elif tache.precedence and tache.precedence not in simulation.tasks_terminees.all():
                taches_bloquees.append({
                    'tache': tache,
                    'raison': 'precedence_non_terminee',
                    'temps_restant': float('inf')  # Inconnu
                })
                
        return taches_bloquees

    # Méthodes internes -----------------------------------------------------
    
    @staticmethod
    def _calculer_score_cout(operateur, tache):
        """Score inversement proportionnel au coût de sous-performance"""
        perf = operateur.performance_set.get(task=tache).valeur
        sous_perf = (tache.temps_standard / perf) - tache.temps_standard
        cout = sous_perf * tache.product.cr
        return 1 - min(cout / 1000, 1)  # Normalisé sur un coût max de 1000€

    @staticmethod
    def _calculer_score_performance(operateur, tache):
        """Score basé sur la performance historique moyenne"""
        return operateur.performance_set.get(task=tache).valeur / 1.15  # Normalisation

    @staticmethod
    def _calculer_score_equite():
        """Mesure l'équité de charge entre opérateurs"""
        temps_travail = list(Operator.objects.values_list('temps_travail', flat=True))
        if not temps_travail:
            return 1.0
        ecart_type = np.std(temps_travail)
        return 1 - min(ecart_type / 480, 1)  # Normalisé sur 8h

    @staticmethod
    def _calculer_score_makespan(simulation, tache):
        """Score inversement proportionnel à l'impact sur le planning global"""
        makespan_courant = simulation.makespan_actuel
        perf = tache.operator.performance_set.get(task=tache).valeur
        fin_estimee = timezone.now() + timezone.timedelta(
            minutes=tache.temps_standard / perf
        )
        impact = (fin_estimee - makespan_courant).total_seconds() / 60
        return 1 - min(impact / 240, 1)  # Normalisé sur 4h max
    