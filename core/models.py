import uuid
from django.db import models


class ContactMessage(models.Model):
    """Stores messages submitted from the contact form."""
    name = models.CharField(max_length=120)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} <{self.email}>"


class DevetryxEvent(models.Model):
    """
    Standard event log model matching Part 2.4 specification.
    Records every meaningful developer action to power Skill Graph & telemetry.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64, db_index=True)
    user_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    session_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["event_type", "timestamp"]),
            models.Index(fields=["session_id", "timestamp"]),
        ]

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.event_type} ({self.session_id or self.user_id or 'anon'})"

    def to_dict(self):
        return {
            "id": str(self.id),
            "event_type": self.event_type,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "payload": self.payload,
        }


class UserSkillSnapshot(models.Model):
    """
    Cached snapshot of calculated Skill Graph conforming to Part 2.1 schema.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    session_id = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    skill_data = models.JSONField(default=dict)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"SkillSnapshot for {self.session_id or self.user_id} @ {self.updated_at}"
