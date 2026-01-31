"""Forms for user settings in the accounts app."""

import json

from django import forms

from .models import SettingProfile, UserSettings


class SettingProfileForm(forms.ModelForm):
    """Form for creating and editing setting profiles."""

    # Hidden field populated by the client-side columns editor
    spreadsheet_columns_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = SettingProfile
        fields = [
            "name",
            "is_default",
            "vignette_prompt",
            "spreadsheet_prompt",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "e.g., Pathology, Cardiology, Anatomy",
                    "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500",
                }
            ),
            "is_default": forms.CheckboxInput(
                attrs={
                    "class": "rounded border-gray-300 text-blue-600 focus:ring-blue-500",
                }
            ),
            "vignette_prompt": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": "Leave blank to use the default prompt",
                    "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm",
                }
            ),
            "spreadsheet_prompt": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": "Leave blank to use the default prompt",
                    "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm",
                }
            ),
        }

    def clean_vignette_prompt(self):
        value = self.cleaned_data.get("vignette_prompt")
        if value and value.strip() == "":
            return None
        return value

    def clean_spreadsheet_prompt(self):
        value = self.cleaned_data.get("spreadsheet_prompt")
        if value and value.strip() == "":
            return None
        return value

    def parse_columns(self) -> list[dict] | None:
        raw = self.cleaned_data.get("spreadsheet_columns_json")
        if not raw:
            return None
        try:
            data = json.loads(raw)
            # Basic validation: list of objects with name/description
            if isinstance(data, list):
                normalized = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    description = str(item.get("description", "")).strip()
                    if name:
                        normalized.append({"name": name, "description": description})
                return normalized
        except json.JSONDecodeError:
            pass
        return None

    def save(self, commit=True):
        instance = super().save(commit=False)
        cols = self.parse_columns()
        if cols is not None:
            instance.spreadsheet_columns = cols
        if commit:
            instance.save()
        return instance


class UserSettingsForm(forms.ModelForm):
    # Hidden field populated by the client-side columns editor
    spreadsheet_columns_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = UserSettings
        fields = [
            "vignette_prompt",
            "spreadsheet_prompt",
        ]
        widgets = {
            "vignette_prompt": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": "Leave blank to use the default prompt",
                    "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500",
                }
            ),
            "spreadsheet_prompt": forms.Textarea(
                attrs={
                    "rows": 10,
                    "placeholder": "Leave blank to use the default prompt",
                    "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500",
                }
            ),
        }

    def clean_vignette_prompt(self):
        value = self.cleaned_data.get("vignette_prompt")
        if value and value.strip() == "":
            return None
        return value

    def clean_spreadsheet_prompt(self):
        value = self.cleaned_data.get("spreadsheet_prompt")
        if value and value.strip() == "":
            return None
        return value

    def parse_columns(self) -> list[dict] | None:
        raw = self.cleaned_data.get("spreadsheet_columns_json")
        if not raw:
            return None
        try:
            data = json.loads(raw)
            # Basic validation: list of objects with name/description
            if isinstance(data, list):
                normalized = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    description = str(item.get("description", "")).strip()
                    if name:
                        normalized.append({"name": name, "description": description})
                return normalized
        except json.JSONDecodeError:
            pass
        return None

    def save(self, commit=True):
        instance = super().save(commit=False)
        cols = self.parse_columns()
        if cols is not None:
            instance.spreadsheet_columns = cols
        if commit:
            instance.save()
        return instance
