# Create some records

await User.query.create(name="Adam", email="adam@saffier.dev")
await User.query.create(name="Eve", email="eve@saffier.dev")

# Query using the multiple or_
await User.query.or_(email__icontains="saffier").or_(name__icontains="a")

# Query using the or_ with multiple fields
await User.query.or_(email__icontains="saffier", name__icontains="a")
