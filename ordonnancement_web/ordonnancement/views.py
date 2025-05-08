import json  # Ajoutez cette ligne en haut du fichier
from django.shortcuts import render, get_object_or_404,redirect
from django.http import JsonResponse
from .forms import OperateurFormSet, MachineFormSet, ProduitFormSet, ParametresForm
from .utils.simulation_runner import SimulationEngine
from .utils.scheduler import  Ordonnanceur
from .utils.gantt_generator import GanttEngine
from .utils.cost_calculator import CostEngine
from .utils.performance_calculator import PerformanceTracker

from .models import Simulation

def lancer_simulation_view(request):
    """Vue principale qui orchestre la simulation complète"""
    if request.method == 'POST':
        try:
            # 1. Initialisation
            config = {
                'operateurs': json.loads(request.POST.get('operateurs', '[]')),
                'taches': json.loads(request.POST.get('taches', '[]')),
                'duree_max': int(request.POST.get('duree_max', 1440))  # Default 24h
            }
            
            # Validation des données
            if not config['operateurs'] or not config['taches']:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Données opérateurs ou tâches manquantes'
                }, status=400)

            simulation = SimulationEngine.demarrer_simulation(config)
            
            # 2. Boucle principale
            pas_temps = 30  # minutes
            while simulation.temps_actuel < simulation.temps_max:
                evenements = SimulationEngine.avancer_temps(simulation, pas_temps)
                
                # Condition d'arrêt si aucun événement à traiter
                if not evenements:
                    break
                
                # Mise à jour des performances
                for event in evenements:
                    if event['evenement'].type == 'FIN_TACHE':
                        PerformanceTracker.mettre_a_jour_performance(
                            operateur=event['evenement'].operateur,
                            tache=event['evenement'].tache,
                            temps_actuel=event['evenement'].temps_planifie
                        )
            
            # 3. Génération des résultats
            resultats = {
                'gantt_operateurs': GanttEngine.generer_donnees_operateurs(simulation),
                'gantt_machines': GanttEngine.generer_donnees_machines(simulation),
                'couts': CostEngine.calculer_cout_global(simulation),
                'performances': PerformanceTracker.analyser_performances(simulation)
            }
            
            # 4. Export des résultats
            try:
                GanttEngine.exporter_vers_excel(
                    resultats['gantt_operateurs'],
                    filename=f"media/gantt_{simulation.id}.xlsx"
                )
            except Exception as e:
                print(f"Erreur lors de l'export Excel: {str(e)}")

            return JsonResponse({
                'status': 'success',
                'simulation_id': simulation.id,
                'results': {
                    'gantt': resultats['gantt_operateurs'][:5],  # Exemple seulement
                    'total_cost': resultats['couts']['total']
                }
            })
            
        except json.JSONDecodeError as e:
            return JsonResponse({
                'status': 'error',
                'message': f"Erreur de format JSON: {str(e)}"
            }, status=400)
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': f"Erreur inattendue: {str(e)}"
            }, status=500)
    
    return render(request, 'simulation/launcher.html')

def afficher_resultats(request, simulation_id):
    """Affiche les résultats détaillés d'une simulation"""
    simulation = get_object_or_404(Simulation, pk=simulation_id)
    
    context = {
        'simulation': simulation,
        'gantt_data': json.dumps(GanttEngine.generer_donnees_operateurs(simulation)),
        'cost_data': CostEngine.generer_rapport_par_operateur(simulation),
        'performance_data': json.dumps(
            PerformanceTracker.get_global_stats(simulation)
        )
    }
    
    return render(request, 'simulation/results.html', context)

def configurer_simulation(request):
    if request.method == 'POST':
        operateur_formset = OperateurFormSet(request.POST, prefix='operateurs')
        machine_formset = MachineFormSet(request.POST, prefix='machines')
        produit_formset = ProduitFormSet(request.POST, prefix='produits')
        parametres_form = ParametresForm(request.POST)

        if all([
            operateur_formset.is_valid(),
            machine_formset.is_valid(),
            produit_formset.is_valid(),
            parametres_form.is_valid()
        ]):
            # Préparation des données pour la simulation
            config = {
                'operateurs': [],
                'machines': [],
                'produits': [],
                'poids': parametres_form.cleaned_data
            }

            for form in operateur_formset:
                config['operateurs'].append({
                    'id': form.cleaned_data['id'],
                    'learning_params': {
                        'LC': form.cleaned_data['lc'],
                        'FC': form.cleaned_data['fc']
                    },
                    'performance_initiale': form.cleaned_data['performance_initiale']
                })

            for form in machine_formset:
                config['machines'].append({
                    'id': form.cleaned_data['id'],
                    'taches_compatibles': [
                        t.strip() for t in form.cleaned_data['taches_compatibles'].split(',')
                    ]
                })

            for form in produit_formset:
                config['produits'].append({
                    'id': form.cleaned_data['id'],
                    'cr': form.cleaned_data['cr'],
                    'taches': [
                        t.strip() for t in form.cleaned_data['taches'].split(',')
                    ]
                })

            # Stockage en session pour la simulation
            request.session['simulation_config'] = config
            return redirect('lancer_simulation')

    else:
        operateur_formset = OperateurFormSet(prefix='operateurs')
        machine_formset = MachineFormSet(prefix='machines')
        produit_formset = ProduitFormSet(prefix='produits')
        parametres_form = ParametresForm()

    context = {
        'operateur_formset': operateur_formset,
        'machine_formset': machine_formset,
        'produit_formset': produit_formset,
        'parametres_form': parametres_form,
    }
    return render(request, 'simulation/config.html', context)


