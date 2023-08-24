assert len(users) == 2  # Total ussers

saffier = [value for value in users if value.pk == saffier.pk][0]
assert len(saffier.to_posts) == 5  # Total posts for Saffier
assert len(saffier.to_articles) == 50  # Total articles for Saffier

esmerald = [value for value in users if value.pk == esmerald.pk][0]
assert len(esmerald.to_posts) == 15  # Total posts for Esmerald
assert len(esmerald.to_articles) == 20  # Total articles for Esmerald
