from django import forms

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    website = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot against spam bots

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "subject", "message"]

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""
