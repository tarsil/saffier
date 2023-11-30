# Create some records

await User.query.create(name="Adam", email="adam@saffier.dev")
await User.query.create(name="Eve", email="eve@saffier.dev")

# Query using the not_
await User.query.not_(email__icontains="saffier").not_(name__icontains="a")
