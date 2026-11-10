from django import forms
from django.contrib.auth.models import User
from .models import UserProfile


MAX_UPLOAD_SIZE = 200 * 1024 * 1024


class UploadDatasetForm(forms.Form):
    file = forms.FileField(label="Historical Incineration Dataset")
    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith((".csv", ".xlsx", ".xls")):
            raise forms.ValidationError("Upload a CSV or Excel file.")
        if f.size > MAX_UPLOAD_SIZE:
            raise forms.ValidationError("Maximum file size is 200 MB.")
        return f


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)

class PredictionSettingsForm(forms.Form):
    algorithm = forms.ChoiceField(choices=[
        ("RANDOM_FOREST", "Random Forest Regressor"),
        ("LINEAR_REGRESSION", "Linear Regression"),
    ])
    target_column = forms.ChoiceField()
    feature_columns = forms.MultipleChoiceField(widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, columns=None, **kwargs):
        super().__init__(*args, **kwargs)
        numeric = columns or []
        self.fields["target_column"].choices = [(c, c) for c in numeric]
        self.fields["feature_columns"].choices = [(c, c) for c in numeric]

class UserCreateForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    department = forms.CharField(max_length=150)
    is_active = forms.ChoiceField(
        choices=(("True", "Active"), ("False", "Inactive")),
        initial="True",
        required=False,
        label="Account status",
    )

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        if len(cleaned.get("password", "")) < 8:
            self.add_error("password", "Use a password with at least 8 characters.")
        return cleaned


class OfficerUpdateForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    department = forms.CharField(max_length=150)
