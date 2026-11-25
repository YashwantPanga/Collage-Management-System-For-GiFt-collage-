from django import forms
from django.utils import timezone

from . import models as m


def current_academic_year():
    today = timezone.localdate()
    start = today.year if today.month >= 6 else today.year - 1
    return f"{start}-{start + 1}"


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None, format="%Y-%m-%d"):
        super().__init__(attrs, format)


class TimeInput(forms.TimeInput):
    input_type = "time"


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = m.Application
        fields = ["course", "full_name", "email", "phone", "date_of_birth", "gender", "category", "guardian_name",
                  "guardian_phone", "address", "previous_institution", "qualifying_exam", "percentage", "entrance_rank"]
        widgets = {"date_of_birth": DateInput(), "address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["course"].queryset = m.Course.objects.filter(is_active=True)


class DocumentForm(forms.ModelForm):
    class Meta:
        model = m.ApplicationDocument
        fields = ["doc_type", "file"]

    def clean_file(self):
        f = self.cleaned_data["file"]
        if f and f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Maximum file size is 5 MB.")
        return f


class EnrollForm(forms.Form):
    batch = forms.ModelChoiceField(queryset=m.Batch.objects.none())
    username = forms.CharField(max_length=150, required=False, help_text="Only needed if the applicant has no login yet.")
    password = forms.CharField(widget=forms.PasswordInput, required=False, min_length=8)

    def __init__(self, application, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["batch"].queryset = m.Batch.objects.filter(course=application.course)
        self.application = application

    def clean(self):
        data = super().clean()
        if not self.application.applicant and not (data.get("username") and data.get("password")):
            raise forms.ValidationError("Applicant has no account: enter a username and initial password.")
        return data


class LeaveForm(forms.ModelForm):
    class Meta:
        model = m.LeaveRequest
        fields = ["leave_type", "from_date", "to_date", "reason"]
        widgets = {"from_date": DateInput(), "to_date": DateInput(), "reason": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        data = super().clean()
        if data.get("from_date") and data.get("to_date") and data["to_date"] < data["from_date"]:
            raise forms.ValidationError("'To date' must be on or after 'From date'.")
        return data


class SessionForm(forms.Form):
    subject = forms.ModelChoiceField(queryset=m.Subject.objects.none())
    batch = forms.ModelChoiceField(queryset=m.Batch.objects.none())
    date = forms.DateField(widget=DateInput(), initial=timezone.localdate)
    period = forms.IntegerField(min_value=1, max_value=10, initial=1)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        subjects = m.Subject.objects.select_related("course")
        if not user.is_superuser and user.role == "faculty":
            subjects = subjects.filter(faculty=user)
        elif user.role == "hod":
            subjects = subjects.filter(course__department_id=user.department_id)
        self.fields["subject"].queryset = subjects
        self.fields["batch"].queryset = m.Batch.objects.filter(course__in=subjects.values("course")).distinct()

    def clean(self):
        data = super().clean()
        if data.get("subject") and data.get("batch") and data["subject"].course_id != data["batch"].course_id:
            raise forms.ValidationError("The batch does not belong to the subject's course.")
        return data


class InvoiceGenerateForm(forms.Form):
    batch = forms.ModelChoiceField(queryset=m.Batch.objects.all())
    semester = forms.IntegerField(min_value=1, max_value=12)
    academic_year = forms.CharField(max_length=9, initial=current_academic_year)


class InvoiceEditForm(forms.ModelForm):
    class Meta:
        model = m.Invoice
        fields = ["tuition_fee", "exam_fee", "other_fee", "scholarship", "concession", "due_date"]
        widgets = {"due_date": DateInput()}


class OfflinePaymentForm(forms.ModelForm):
    class Meta:
        model = m.Payment
        fields = ["amount", "method", "transaction_id"]
        labels = {"transaction_id": "Reference / DD / UTR no."}


class RefundForm(forms.ModelForm):
    class Meta:
        model = m.Refund
        fields = ["invoice", "payment", "amount", "reason"]


class MarksSelectForm(forms.Form):
    exam = forms.ModelChoiceField(queryset=m.Exam.objects.filter(is_published=False))
    subject = forms.ModelChoiceField(queryset=m.Subject.objects.none())

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        subjects = m.Subject.objects.select_related("course")
        if user.role == "faculty":
            subjects = subjects.filter(faculty=user)
        self.fields["subject"].queryset = subjects
        self.fields["exam"].queryset = m.Exam.objects.filter(is_published=False, course__in=subjects.values("course")).distinct()

    def clean(self):
        data = super().clean()
        exam, subject = data.get("exam"), data.get("subject")
        if exam and subject and (subject.course_id != exam.course_id or subject.semester != exam.semester):
            raise forms.ValidationError("This subject is not part of the selected exam's course/semester.")
        return data


class RevaluationForm(forms.ModelForm):
    class Meta:
        model = m.Revaluation
        fields = ["reason"]
        widgets = {"reason": forms.Textarea(attrs={"rows": 3})}


class PlacementProfileForm(forms.ModelForm):
    class Meta:
        model = m.PlacementProfile
        fields = ["is_registered", "resume", "skills", "linkedin", "github", "summary"]
        labels = {"is_registered": "Register me for campus placements"}
        widgets = {"summary": forms.Textarea(attrs={"rows": 4})}


class JobForm(forms.ModelForm):
    class Meta:
        model = m.JobPosting
        fields = ["company", "title", "description", "location", "package_lpa", "vacancies", "eligible_courses",
                  "min_cgpa", "max_backlogs", "min_attendance", "deadline", "is_open"]
        widgets = {"deadline": DateInput(), "description": forms.Textarea(attrs={"rows": 5}),
                   "eligible_courses": forms.SelectMultiple(attrs={"size": 6})}

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if user.role == "recruiter":
            self.fields["company"].queryset = m.Company.objects.filter(recruiters=user)


class StageForm(forms.ModelForm):
    class Meta:
        model = m.PlacementApplication
        fields = ["stage", "interview_at", "offered_package", "offer_letter", "remarks"]
        widgets = {"interview_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}
