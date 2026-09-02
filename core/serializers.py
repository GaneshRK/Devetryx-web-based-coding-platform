"""
Devetryx DRF Serializers.
"""

from rest_framework import serializers
from .models import DevetryxEvent, ContactMessage


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ["id", "name", "email", "message", "created_at"]


class DevetryxEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DevetryxEvent
        fields = ["id", "event_type", "user_id", "session_id", "timestamp", "payload"]


class RunCodeSerializer(serializers.Serializer):
    files = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        help_text="Dictionary of filename to content string"
    )
    main_file = serializers.CharField(default="main.py")
    user_input = serializers.CharField(default="", allow_blank=True, required=False)
    session_id = serializers.CharField(required=False, allow_blank=True, default="")
    mode = serializers.CharField(required=False, default="compiler")


class AIMentorRequestSerializer(serializers.Serializer):
    user_question = serializers.CharField(required=False, allow_blank=True, default="")
    current_file = serializers.CharField(default="main.py")
    code = serializers.CharField(required=False, allow_blank=True, default="")
    files = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=dict
    )
    recent_execution = serializers.DictField(required=False, default=dict)
    assistance_level = serializers.IntegerField(default=2, min_value=1, max_value=5)
    session_id = serializers.CharField(required=False, allow_blank=True, default="")
