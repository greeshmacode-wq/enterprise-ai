from django import forms
from accounts.models import User

class LoginForm(forms.Form):
    username = forms.CharField(max_length=150,widget=forms.TextInput(attrs={ "class": "form-control",'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={ "class": "form-control",'placeholder': 'Password'}))
    # widget to control the HTML, CSS, and user experience (like hiding passwords, adding Bootstrap classes, or adding placeholder text),