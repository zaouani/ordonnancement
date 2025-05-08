from django.urls import path
from . import views

app_name = 'ordonnancement'

urlpatterns = [
    #page de configuration
    path('configurer/', views.configurer_simulation, name='configurer_simulation'),

    # Page de lancement de simulation
    path('simulation/', views.lancer_simulation_view, name='lancer_simulation'),
    
    # Visualisation des résultats
    path('simulation/results/<int:simulation_id>/', 
         views.afficher_resultats, 
         name='afficher_resultats'),
    
]