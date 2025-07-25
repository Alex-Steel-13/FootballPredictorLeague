# Generated by Django 5.2.2 on 2025-07-13 15:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leaderboard', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leaderboardentry',
            name='correct_predictions',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='leaderboardentry',
            name='number_of_predictions',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='leaderboardentry',
            name='perfect_predictions',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='leaderboardentry',
            name='score',
            field=models.IntegerField(default=0),
        ),
    ]
