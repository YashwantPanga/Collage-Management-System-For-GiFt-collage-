from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import SELF_REGISTER_ROLES, Role

User = get_user_model()


class LoginForm(forms.Form):
    username = forms.CharField(label="Username or email", max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    remember = forms.BooleanField(required=False, initial=True, label="Keep me signed in")

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        ident, pwd = data.get("username", "").strip(), data.get("password")
        if ident and pwd:
            if "@" in ident:
                match = User.objects.filter(email__iexact=ident).first()
                ident = match.username if match else ident
            self.user = authenticate(self.request, username=ident, password=pwd)
            if self.user is None:
                raise forms.ValidationError("Invalid username/email or password.")
            if not self.user.is_active:
                raise forms.ValidationError("This account is disabled.")
        return data


class RegisterForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=[(r.value, r.label) for r in SELF_REGISTER_ROLES], initial=Role.STUDENT, label="I am a",
        help_text="Students apply for admission; parents track their ward; recruiters post jobs.",
    )
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("role", "first_name", "last_name", "username", "email", "phone")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "avatar"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is used by another account.")
        return email
