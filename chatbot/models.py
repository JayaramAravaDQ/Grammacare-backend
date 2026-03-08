from django.db import models


class Consultation(models.Model):
    """Stores a consultation summary for history (matches frontend ConsultationSummary)."""
    consultation_id = models.CharField(max_length=120, unique=True, db_index=True)
    username = models.CharField(max_length=200)
    symptom = models.CharField(max_length=200)
    disease = models.CharField(max_length=200)
    severity_level = models.CharField(max_length=50)
    date = models.DateTimeField()
    messages = models.JSONField(default=list)  # list of {role, content, timestamp}
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
