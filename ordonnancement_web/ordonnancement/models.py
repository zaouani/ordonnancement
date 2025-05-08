from django.db import models
from django.core.validators import MinValueValidator

class Operator(models.Model):
    """Modèle pour les opérateurs, correspondant à la classe Operator"""
    id = models.CharField(max_length=10, primary_key=True, verbose_name="ID Opérateur")
    learning_params_lc = models.FloatField(verbose_name="Paramètre d'apprentissage LC")
    learning_params_fc = models.FloatField(verbose_name="Paramètre d'oubli FC")
    initial_performance = models.FloatField(default=1.0, verbose_name="Performance initiale")
    temps_inactif = models.FloatField(default=0, verbose_name="Temps inactif (min)")
    temps_travail = models.FloatField(default=0, verbose_name="Temps de travail (min)")

    class Meta:
        verbose_name = "Opérateur"
        verbose_name_plural = "Opérateurs"

    def __str__(self):
        return f"Opérateur {self.id}"

class Product(models.Model):
    """Modèle pour les produits"""
    id = models.CharField(max_length=10, primary_key=True, verbose_name="ID Produit")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)], verbose_name="Quantité")
    cr = models.FloatField(verbose_name="Coût de sous-performance (€/min)")

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"

    def __str__(self):
        return f"Produit {self.id}"

class Machine(models.Model):
    """Modèle pour les machines"""
    id = models.CharField(max_length=10, primary_key=True, verbose_name="ID Machine")
    taches_compatibles = models.JSONField(default=list, verbose_name="Tâches compatibles")
    temps_setup = models.FloatField(default=0, verbose_name="Temps de setup (min)")

    class Meta:
        verbose_name = "Machine"
        verbose_name_plural = "Machines"

    def __str__(self):
        return f"Machine {self.id}"

class Task(models.Model):
    """Modèle pour les tâches"""
    id = models.CharField(max_length=10, primary_key=True, verbose_name="ID Tâche")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='taches')
    phase = models.PositiveIntegerField(verbose_name="Phase")
    precedence = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Tâche précédente")
    temps_standard = models.FloatField(verbose_name="Temps standard (min)")
    machine_requise = models.ForeignKey(Machine, on_delete=models.CASCADE, verbose_name="Machine requise")
    quantite = models.PositiveIntegerField(verbose_name="Quantité")
    cr = models.FloatField(verbose_name="Coût de sous-performance")
    
    # Champs dynamiques (peuvent être calculés)
    temps_reel = models.FloatField(default=0, verbose_name="Temps réel (min)")
    temps_attente = models.FloatField(default=0, verbose_name="Temps d'attente (min)")
    est_en_cours = models.BooleanField(default=False, verbose_name="En cours")

    class Meta:
        verbose_name = "Tâche"
        verbose_name_plural = "Tâches"
        ordering = ['phase']

    def __str__(self):
        return f"Tâche {self.id} (Produit {self.product.id})"

class OperatorPerformance(models.Model):
    """Historique des performances par opérateur/tâche"""
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name='performances')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    performance = models.FloatField(verbose_name="Performance (0-1)")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Date/heure")

    class Meta:
        verbose_name = "Performance opérateur"
        verbose_name_plural = "Performances opérateurs"
        unique_together = ('operator', 'task', 'timestamp')

class WorkHistory(models.Model):
    """Historique de travail des opérateurs"""
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name='historique_travail')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    debut = models.DateTimeField(verbose_name="Début")
    fin = models.DateTimeField(null=True, blank=True, verbose_name="Fin")
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name = "Historique travail"
        verbose_name_plural = "Historiques travail"
        ordering = ['-debut']

class MachineHistory(models.Model):
    """Historique d'utilisation des machines"""
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='historique')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE)
    debut = models.DateTimeField(verbose_name="Début")
    fin = models.DateTimeField(verbose_name="Fin")

    class Meta:
        verbose_name = "Historique machine"
        verbose_name_plural = "Historiques machines"
        ordering = ['-debut']

class Simulation(models.Model):
    """Configuration et résultats d'une simulation"""
    nom = models.CharField(max_length=100, verbose_name="Nom de la simulation")
    date_creation = models.DateTimeField(auto_now_add=True)
    temps_actuel = models.FloatField(default=0, verbose_name="Temps actuel (min)")
    makespan_actuel = models.FloatField(default=0, verbose_name="Makespan (min)")
    temps_max = models.FloatField(default=1440, verbose_name="Temps max (min)")
    
    # Relations
    tasks_terminees = models.ManyToManyField(Task, blank=True, verbose_name="Tâches terminées")

    class Meta:
        verbose_name = "Simulation"
        verbose_name_plural = "Simulations"
        ordering = ['-date_creation']

class Cost(models.Model):
    """Suivi des coûts de sous-performance"""
    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE, related_name='couts')
    total_sous_performance = models.FloatField(default=0, verbose_name="Coût total (€)")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Coût"
        verbose_name_plural = "Coûts"

class CostDetail(models.Model):
    """Détail des coûts par opérateur/tâche"""
    cost = models.ForeignKey(Cost, on_delete=models.CASCADE, related_name='details')
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, null=True, blank=True)
    montant = models.FloatField(verbose_name="Montant (€)")
    type_cout = models.CharField(max_length=50, choices=[
        ('sous_performance', 'Sous-performance'),
        ('attente', 'Temps d\'attente')
    ])

    class Meta:
        verbose_name = "Détail coût"
        verbose_name_plural = "Détails coûts"

class Evenement(models.Model):
    """Modèle pour les événements du système de simulation"""
    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE, related_name='evenements')
    type_evenement = models.CharField(max_length=50, choices=[
        ('debut_tache', 'Début de tâche'),
        ('fin_tache', 'Fin de tâche'),
        ('arret', 'Arrêt de simulation')
    ])
    timestamp = models.FloatField(verbose_name="Temps (min)")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, null=True, blank=True)
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Événement"
        verbose_name_plural = "Événements"
        ordering = ['timestamp']

    def __str__(self):
        return f"Événement {self.type_evenement} à t={self.timestamp}"

class TaskAssignment(models.Model):
    """Assignation d'une tâche à un opérateur avec suivi temporel"""
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name='assignations')
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='assignations')
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True)
    debut = models.DateTimeField(verbose_name="Début")
    fin = models.DateTimeField(verbose_name="Fin")
    temps_reel = models.FloatField(verbose_name="Temps réel (min)")
    est_terminee = models.BooleanField(default=False, verbose_name="Terminée")

    class Meta:
        verbose_name = "Assignation de tâche"
        verbose_name_plural = "Assignations de tâches"
        ordering = ['-debut']
        
    def __str__(self):
        return f"{self.operator.id} → {self.task.id} ({self.debut})"