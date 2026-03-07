# Shell Support

Who never needed to load a few database models ina command line  or have the need to do it so and
got stuck trying to do it and wasted a lot of time?

Well, Saffier gives you that possibility completely out of the box and ready to use with your
application models.

!!! Warning
    Be aware of the use of this special class in production! It is advised not to use it there.

## Important

Before reading this section, you should get familiar with the ways Saffier handles the discovery
of the applications.

The following examples and explanations will be using the [auto discovery](./migrations/discovery.md#auto-discovery)
but [--app and environment variables](./migrations/discovery.md##environment-variables) approach but the
is equally valid and works in the same way.

!!! Tip
    See the [extras](./extras.md) section after getting familiar with the previous. There offers
    a way of using the shell without going through the deprecated **Migrate** wrapper.

## How does it work

Saffier ecosystem is complex internally but simpler to the user. Saffier will use the active
`Instance`, resolve the [registry](./registry.md) from it, and then load models and reflected
models into the shell.

From there it will automatically load the [models](./models.md) and [reflected models](./reflection.md)
into the interactive python shell and load them for you with ease 🎉.

### Requirements

To run any of the available shells you will need `ipython` or `ptpython` or both installed.

**IPython**

```shell
$ pip install ipython
```

or

```shell
$ pip install saffier[ipython]
```

**PTPython**

```shell
$ pip install ptpython
```

or

```shell
$ pip install saffier[ptpyton]
```

### How to call it

#### With [auto discovery](./migrations/discovery.md#auto-discovery)

**Default shell**

```shell
$ saffier shell
```

**PTPython shell**

```shell
$ saffier shell --kernel ptpython
```

#### With [--app and environment variables](./migrations/discovery.md##environment-variables)

**--app**

```shell
$ saffier --app myproject.main shell
```

**Environment variables**

```shell
$ export SAFFIER_DEFAULT_APP=myproject.main
$ saffier shell --kernel ptpython
```

### How does it look like

Saffier doesn't want to load all python globals and locals for you. Instead loads all the
essentials for the models and reflected models and some python packages.

It looks like this:

<img src="https://res.cloudinary.com/dymmond/image/upload/v1682083526/Saffier/carbon/shell_n2ruox.png" alt='Shell Example'>

Of course the `SAFFIER-VERSION` and `APPLICATION` are replaced automatically by the version you are
using.

#### Example

Let us see an example using example using Ravyn and we will have:

* Three [models](./models.md):
    * User - From an [ravyn application][ravyn_application] `accounts`.
    * Customer - From an [ravyn application][ravyn_application] `customers`.
    * Product - From an [ravyn application][ravyn_application] `products`.
* Two [reflected models](./reflection.md):
    * Payment - From a payments table reflected from the existing database.
    * RecordView - From a SQL View reflected from the existing database.

And it will look like this:

<img src="https://res.cloudinary.com/dymmond/image/upload/v1682084269/Saffier/carbon/example_m2ggyt.png" alt='Shell Example'>

Pretty cool, right? Then it is a normal python shell where you can import whatever you want and
need as per normal python shell interaction.

[ravyn_application]: https://ravyn.dymmond.com/management/directives/#create-app
