from django import forms
from django.forms import formset_factory

class OperateurForm(forms.Form):
    id = forms.CharField(label="ID Opérateur", max_length=10)
    lc = forms.FloatField(label="Paramètre d'apprentissage (LC)", min_value=0.1, max_value=1.0, initial=0.8)
    fc = forms.FloatField(label="Paramètre d'oubli (FC)", min_value=0.01, max_value=0.5, initial=0.1)
    performance_initiale = forms.FloatField(label="Performance initiale", min_value=0.1, max_value=1.0, initial=0.6)

class MachineForm(forms.Form):
    id = forms.CharField(label="ID Machine", max_length=10)
    taches_compatibles = forms.CharField(
        label="Tâches compatibles (séparées par des virgules)", 
        help_text="Ex: T1,T2,T3"
    )

class ProduitForm(forms.Form):
    id = forms.CharField(label="ID Produit", max_length=10)
    cr = forms.FloatField(label="Coût de sous-performance (€/min)", min_value=0)
    taches = forms.CharField(
        label="Séquence des tâches (séparées par des virgules)", 
        help_text="Ex: T1,T2,T3"
    )

class ParametresForm(forms.Form):
    poids_performance = forms.FloatField(
        label="Poids Performance", 
        min_value=0, 
        max_value=1, 
        initial=0.2,
        widget=forms.NumberInput(attrs={'step': "0.01"})
    )
    poids_cout = forms.FloatField(label="Poids Coût", min_value=0, max_value=1, initial=0.4)
    poids_makespan = forms.FloatField(label="Poids Makespan", min_value=0, max_value=1, initial=0.2)
    poids_equite = forms.FloatField(label="Poids Équité", min_value=0, max_value=1, initial=0.2)

    def clean(self):
        cleaned_data = super().clean()
        total = sum([
            cleaned_data.get('poids_performance', 0),
            cleaned_data.get('poids_cout', 0),
            cleaned_data.get('poids_makespan', 0),
            cleaned_data.get('poids_equite', 0)
        ])
        
        if not (0.99 <= total <= 1.01):
            raise forms.ValidationError("La somme des poids doit être égale à 1")
        return cleaned_data

# Formsets pour les entrées multiples
OperateurFormSet = formset_factory(OperateurForm, extra=1)
MachineFormSet = formset_factory(MachineForm, extra=1)
ProduitFormSet = formset_factory(ProduitForm, extra=1)