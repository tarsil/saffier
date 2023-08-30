import saffier

database = saffier.Database("sqlite:///db.sqlite")
registry = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.BigIntegerField(primary_key=True)
    name = saffier.CharField(max_length=255)
    email = saffier.CharField(max_length=255)

    class Meta:
        registry = registry


# Create the custom signal
User.meta.signals.on_verify = saffier.Signal()


# Create the receiver
async def trigger_notifications(sender, instance, **kwargs):
    """
    Sends email and push notification
    """
    send_email(instance.email)
    send_push_notification(instance.email)


# Register the receiver into the new Signal.
User.meta.signals.on_verify.connect(trigger_notifications)
