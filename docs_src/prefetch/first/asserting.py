assert len(users) == 2  # Total ussers

saffier = [value for value in users if value.pk == saffier.pk][0]
assert len(saffier.to_posts) == 5  # Total posts for Saffier
assert len(saffier.to_articles) == 50  # Total articles for Saffier

ravyn = [value for value in users if value.pk == ravyn.pk][0]
assert len(ravyn.to_posts) == 15  # Total posts for Ravyn
assert len(ravyn.to_articles) == 20  # Total articles for Ravyn
