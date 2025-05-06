from django.db.models import (
    Sum, 
    F, 
    FloatField, 
    ExpressionWrapper,
    Count,
    Prefetch  
)
from django.db.models.functions import Coalesce
from collections import defaultdict
from ..models import Simulation, TaskAssignment, Operator, Product, Task  


class CostEngine:
    
    @staticmethod
    def calculer_cout_global(simulation):
        """
        Calcule le coût total de sous-performance pour une simulation
        Args:
            simulation: Instance du modèle Simulation
        Returns:
            {
                'total': float (coût total en €),
                'par_operateur': {op_id: float},
                'par_produit': {product_id: float}
            }
        """
        # Calcul des coûts par assignation
        assignments = TaskAssignment.objects.filter(
            simulation=simulation
        ).annotate(
            sous_performance=ExpressionWrapper(
                F('temps_reel') - F('task__temps_standard'),
                output_field=FloatField()
            ),
            cout=ExpressionWrapper(
                (F('temps_reel') - F('task__temps_standard')) * F('task__product__cr'),
                output_field=FloatField()
            )
        )
        
        # Agrégations
        cout_total = assignments.aggregate(
            total=Coalesce(Sum('cout'), 0.0)
        )['total']
        
        couts_operateurs = assignments.values(
            'operator__id'
        ).annotate(
            total=Sum('cout')
        ).order_by('-total')
        
        couts_produits = assignments.values(
            'task__product__id'
        ).annotate(
            total=Sum('cout')
        ).order_by('-total')
        
        # Formatage des résultats
        return {
            'total': round(cout_total, 2),
            'par_operateur': {item['operator__id']: round(item['total'], 2) for item in couts_operateurs},
            'par_produit': {item['task__product__id']: round(item['total'], 2) for item in couts_produits}
        }

    @staticmethod
    def generer_rapport_par_operateur(simulation_id):
        """
        Génère un rapport détaillé des coûts par opérateur
        Args:
            simulation_id: ID de la simulation
        Returns:
            [
                {
                    'operateur': str (id),
                    'nombre_taches': int,
                    'temps_standard_total': float,
                    'temps_reel_total': float,
                    'sous_performance_total': float (min),
                    'cout_total': float (€),
                    'taches': [
                        {
                            'task_id': str,
                            'sous_performance': float,
                            'cout': float
                        },
                        ...
                    ]
                },
                ...
            ]
        """
        operators = Operator.objects.filter(
            taskassignment__simulation_id=simulation_id
        ).distinct().prefetch_related(
            Prefetch('taskassignment_set',
                   queryset=TaskAssignment.objects.filter(
                       simulation_id=simulation_id
                   ).select_related('task', 'task__product'))
        )
        
        rapport = []
        
        for operator in operators:
            operator_data = {
                'operateur': operator.id,
                'taches': [],
                'temps_standard_total': 0,
                'temps_reel_total': 0
            }
            
            for assignment in operator.taskassignment_set.all():
                sous_perf = assignment.temps_reel - assignment.task.temps_standard
                cout = sous_perf * assignment.task.product.cr
                
                operator_data['taches'].append({
                    'task_id': assignment.task.id,
                    'sous_performance': round(sous_perf, 2),
                    'cout': round(cout, 2)
                })
                
                operator_data['temps_standard_total'] += assignment.task.temps_standard
                operator_data['temps_reel_total'] += assignment.temps_reel
            
            operator_data['sous_performance_total'] = round(
                operator_data['temps_reel_total'] - operator_data['temps_standard_total'], 2)
            
            operator_data['cout_total'] = round(sum(
                t['cout'] for t in operator_data['taches']), 2)
            
            operator_data['nombre_taches'] = len(operator_data['taches'])
            rapport.append(operator_data)
        
        return sorted(rapport, key=lambda x: x['cout_total'], reverse=True)

    @staticmethod
    def generer_rapport_par_produit(simulation_id):
        """
        Analyse les coûts regroupés par produit
        Args:
            simulation_id: ID de la simulation
        Returns:
            {
                'produits': [
                    {
                        'product_id': str,
                        'quantite': int,
                        'cout_unitaire_moyen': float,
                        'cout_total': float,
                        'taches': [
                            {
                                'task_id': str,
                                'occurrences': int,
                                'cout_total': float
                            },
                            ...
                        ]
                    },
                    ...
                ],
                'stats': {
                    'produit_plus_couteux': str,
                    'cout_max': float,
                    'cout_moyen_par_produit': float
                }
            }
        """
        products = Product.objects.filter(
            task__taskassignment__simulation_id=simulation_id
        ).distinct().prefetch_related(
            Prefetch('task_set',
                   queryset=Task.objects.filter(
                       taskassignment__simulation_id=simulation_id
                   ).annotate(
                       occurrences=Count('taskassignment'),
                       cout_total=Sum(
                           (F('taskassignment__temps_reel') - F('temps_standard')) * 
                           F('product__cr')
                       )
                   ))
        )
        
        rapport = {'produits': [], 'stats': defaultdict(float)}
        cout_total_global = 0
        produits_data = []
        
        for product in products:
            product_data = {
                'product_id': product.id,
                'quantite': product.quantity,
                'taches': [],
                'cout_total': 0
            }
            
            for task in product.task_set.all():
                product_data['taches'].append({
                    'task_id': task.id,
                    'occurrences': task.occurrences,
                    'cout_total': round(task.cout_total, 2) if task.cout_total else 0
                })
                product_data['cout_total'] += round(task.cout_total, 2) if task.cout_total else 0
            
            product_data['cout_unitaire_moyen'] = round(
                product_data['cout_total'] / product_data['quantite'], 2) if product_data['quantite'] > 0 else 0
            
            produits_data.append(product_data)
            cout_total_global += product_data['cout_total']
        
        # Tri par coût décroissant
        rapport['produits'] = sorted(
            produits_data, 
            key=lambda x: x['cout_total'], 
            reverse=True
        )
        
        # Calcul des stats
        if rapport['produits']:
            rapport['stats']['produit_plus_couteux'] = rapport['produits'][0]['product_id']
            rapport['stats']['cout_max'] = rapport['produits'][0]['cout_total']
            rapport['stats']['cout_moyen_par_produit'] = round(
                cout_total_global / len(rapport['produits']), 2)
        
        return rapport