# `Signal`

Signals are Saffier's event hooks around model lifecycle operations.

They are most commonly used for:

* side effects around save or delete operations
* keeping denormalized data in sync
* integrating logging, auditing, or background work with ORM events

## Common built-in lifecycle signals

Model broadcasters expose these built-in hooks:

* `pre_save`
* `post_save`
* `pre_update`
* `post_update`
* `pre_delete`
* `post_delete`

Use the guide page for the narrative walkthrough:
[Signals](../signals.md)

::: saffier.Signal
    options:
        filters:
        - "!^model_config"
        - "!^__slots__"
        - "!^__getattr__"
