"""
Management command to register Celery Beat periodic tasks.
Run once after first migration: python manage.py setup_beat
"""
import json
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Register Celery Beat periodic tasks in the database."

    def handle(self, *args, **options):
        from django_celery_beat.models import CrontabSchedule, PeriodicTask

        # Monthly usage reset: 00:00 on the 1st of every month
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="0",
            day_of_month="1",
            month_of_year="*",
            day_of_week="*",
        )
        task, created = PeriodicTask.objects.get_or_create(
            name="monthly-usage-reset",
            defaults={
                "crontab": schedule,
                "task": "apps.content.tasks.monthly_usage_reset",
                "args": json.dumps([]),
            },
        )
        if not created:
            task.crontab = schedule
            task.save()

        self.stdout.write(self.style.SUCCESS("Beat tasks registered successfully."))
