import math
from django.utils import timezone
from django.db.models import Count, Avg
from ..models import Operator, Task, OperatorPerformance

class PerformanceTracker:
    
    @staticmethod
    def mettre_a_jour_performance(operateur, tache, temps_actuel):
        """
        Met à jour la performance d'un opérateur pour une tâche spécifique
        en appliquant les effets d'apprentissage et d'oubli.
        
        Args:
            operateur: Instance du modèle Operator
            tache: Instance du modèle Task
            temps_actuel: datetime.datetime
            
        Returns:
            float: Nouvelle valeur de performance (entre 0 et 1.15)
        """
        # 1. Calculer le nombre de répétitions
        x = PerformanceTracker.compter_repetitions(operateur.id, tache.id)
        
        # 2. Calculer la durée d'interruption
        y = PerformanceTracker.calculer_interruption(operateur.id, tache.id, temps_actuel)
        
        # 3. Appliquer les formules d'apprentissage/oubli
        b = math.log(operateur.learning_params_lc) / math.log(2)
        
        # Effet d'apprentissage (si répétitions > 0)
        effet_apprentissage = x ** -b if x > 0 else 1.0
        
        # Effet d'oubli (si interruption > 1 jour)
        effet_oubli = math.exp(-operateur.learning_params_fc * max(0, y - 1))
        
        # Nouvelle performance (bornée entre 0 et 1.15)
        nouvelle_performance = min(1.15, max(0, operateur.initial_performance * effet_apprentissage * effet_oubli))
        
        # Sauvegarde en base
        OperatorPerformance.objects.create(
            operator=operateur,
            task=tache,
            performance=nouvelle_performance,
            timestamp=temps_actuel
        )
        
        return nouvelle_performance

    @staticmethod
    def calculer_interruption(operateur_id, tache_id, temps_actuel):
        """
        Calcule en jours la durée depuis la dernière exécution d'une tâche.
        
        Args:
            operateur_id: ID de l'opérateur
            tache_id: ID de la tâche
            temps_actuel: datetime.datetime
            
        Returns:
            float: Nombre de jours écoulés (0 si première exécution)
        """
        derniere_exec = OperatorPerformance.objects.filter(
            operator_id=operateur_id,
            task_id=tache_id
        ).order_by('-timestamp').first()
        
        if not derniere_exec:
            return 0.0
            
        delta = temps_actuel - derniere_exec.timestamp
        return delta.total_seconds() / (24 * 3600)  # Conversion en jours

    @staticmethod
    def compter_repetitions(operateur_id, tache_id):
        """
        Compte le nombre d'exécutions précédentes d'une tâche par un opérateur.
        
        Args:
            operateur_id: ID de l'opérateur
            tache_id: ID de la tâche
            
        Returns:
            int: Nombre d'exécutions antérieures
        """
        return OperatorPerformance.objects.filter(
            operator_id=operateur_id,
            task_id=tache_id
        ).count()

    @staticmethod
    def get_performance_moyenne(operateur_id, tache_id, fenetre=5):
        """
        Calcule la performance moyenne sur les N dernières exécutions.
        
        Args:
            operateur_id: ID de l'opérateur
            tache_id: ID de la tâche
            fenetre: Nombre de derniers essais à considérer
            
        Returns:
            float: Moyenne des performances (0.35 par défaut si aucune donnée)
        """
        performances = OperatorPerformance.objects.filter(
            operator_id=operateur_id,
            task_id=tache_id
        ).order_by('-timestamp')[:fenetre].aggregate(avg=Avg('performance'))
        
        return performances['avg'] or 0.35  # Valeur par défaut si None