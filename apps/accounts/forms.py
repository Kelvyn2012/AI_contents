from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    company = forms.CharField(max_length=200, required=False, help_text="Optional")

    class Meta:
        model = User
        fields = ("username", "email", "company", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            user.profile.company = self.cleaned_data.get("company", "")
            user.profile.save()
        return user


class LoginForm(AuthenticationForm):
    pass
