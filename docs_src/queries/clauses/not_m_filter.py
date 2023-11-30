import saffier

# Create some records

await User.query.create(name="Adam", email="adam@saffier.dev")
await User.query.create(name="Eve", email="eve@saffier.dev")
await User.query.create(name="John", email="john@example.com")

# Query using the not_
await User.query.filter(saffier.not_(User.columns.name == "Adam")).filter(
    saffier.not_(User.columns.email.contains("saffier"))
)
