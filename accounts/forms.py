from django import forms
from django.contrib.auth import authenticate
from .models import User


class RegisterForm(forms.ModelForm):
    """Form for user registration."""

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter password'}),
        min_length=8,
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm password'}),
    )

    class Meta:
        model = User
        fields = ['email', 'full_name']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Dr. / Adv. Full Name'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email').lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    """Form for user login using email."""

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter password'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            email = email.lower().strip()
            user = authenticate(username=email, password=password)
            if not user:
                raise forms.ValidationError("Invalid email or password.")
            if not user.is_active:
                raise forms.ValidationError("This account is currently disabled.")
            cleaned_data['user'] = user

        return cleaned_data


class ProfileForm(forms.ModelForm):
    """Form for updating user profile info."""

    class Meta:
        model = User
        fields = ['full_name']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
        }
