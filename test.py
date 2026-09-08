from accounts.models import UserSigningKey

key = UserSigningKey.objects.get(user__username="YOUR_SHO_USERNAME")

print(len(key.private_key))
print(key.public_key[:50])