from django import forms
from .models import Project, ContentGeneration, CONTENT_TYPES, TONE_CHOICES


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ("name", "brand_name", "tone", "audience", "keywords")
        widgets = {
            "audience": forms.Textarea(attrs={"rows": 3}),
            "keywords": forms.Textarea(attrs={"rows": 2, "placeholder": "e.g. productivity, SaaS, remote work"}),
        }


class GenerateContentForm(forms.Form):
    content_type = forms.ChoiceField(choices=CONTENT_TYPES, label="Content Template")
    prompt_extra = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Additional instructions (optional)"}),
        required=False,
        label="Extra Instructions",
    )


class EditContentForm(forms.Form):
    result_text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 20, "class": "font-mono"}),
        label="Content",
    )
