import saffier

# Create some records

await User.query.create(name="Adam", email="adam@saffier.dev")
await User.query.create(name="Eve", email="eve@saffier.dev")

# Query using the or_
await User.query.filter(saffier.or_(User.columns.name == "Adam")).filter(
    saffier.or_(User.columns.email == "adam@saffier.dev")
)
