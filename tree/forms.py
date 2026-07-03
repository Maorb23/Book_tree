from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import UserProfile


class EmailUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        help_text='Use an email address you can verify.',
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.is_active = False
        if commit:
            user.save()
        return user


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('display_name', 'bio', 'avatar_symbol')
        widgets = {
            'display_name': forms.TextInput(attrs={
                'placeholder': 'Your reading name',
                'maxlength': 120,
            }),
            'bio': forms.Textarea(attrs={
                'placeholder': 'A short note about your reading forest',
                'rows': 4,
            }),
            'avatar_symbol': forms.RadioSelect,
        }
