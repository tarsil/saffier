# Create some records

await User.query.create(name="Adam", email="adam@saffier.dev")
await User.query.create(name="Eve", email="eve@saffier.dev")

# Query using the or_
await User.query.or_(name="Adam").filter(email="adam@saffier.dev")
