from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import AppUser
from .usernames import validate_username

MAX_AVATAR_BYTES = 5 * 1024 * 1024
AVATAR_SIZE = 512
AVATAR_FORMATS = {'JPEG', 'PNG', 'WEBP'}


def change_username(user, username):
    """Returns the old username. Raises ValidationError when it can't be used"""
    with transaction.atomic():
        user = AppUser.objects.select_for_update().get(pk=user.pk)
        username = validate_username(username, user)
        old = user.username
        user.username = username
        try:
            with transaction.atomic():
                user.save(update_fields=['username'])
        except IntegrityError:
            # Someone took it between the check and the save
            raise ValidationError('This username is already taken.', code='taken')
    return old


def optimize_avatar(upload):
    """
    The app sends a picture the user already cropped. Keep their framing:
    make sure it is a real image, fix the rotation, drop the metadata, and
    shrink it to a small square JPEG.
    """
    if upload.size > MAX_AVATAR_BYTES:
        raise ValidationError('The picture must be 5 MB or smaller.', code='too_large')
    try:
        image = Image.open(upload)
        image.verify()  # leaves the image unusable, so open it again
        upload.seek(0)
        image = Image.open(upload)
        if image.format not in AVATAR_FORMATS:
            raise ValidationError('Use a JPEG, PNG or WEBP picture.', code='invalid_format')
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
        raise ValidationError('This file is not a picture.', code='invalid_image')

    if image.mode in ('RGBA', 'LA', 'P'):
        image = image.convert('RGBA')
        background = Image.new('RGB', image.size, 'white')
        background.paste(image, mask=image.getchannel('A'))
        image = background
    else:
        image = image.convert('RGB')

    # Old app versions and direct API calls may send a non-square picture
    image = ImageOps.fit(image, (min(image.size),) * 2, Image.LANCZOS)
    if image.width > AVATAR_SIZE:
        image = image.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

    out = BytesIO()
    image.save(out, 'JPEG', quality=82, optimize=True, progressive=True)
    return ContentFile(out.getvalue())


def set_avatar(user, upload):
    content = optimize_avatar(upload)
    old = user.profile_picture.name if user.profile_picture else None
    user.profile_picture.save('avatar.jpg', content, save=True)
    if old:
        storage = user.profile_picture.storage
        transaction.on_commit(lambda: storage.delete(old))


def remove_avatar(user):
    if not user.profile_picture:
        return
    old = user.profile_picture.name
    storage = user.profile_picture.storage
    user.profile_picture = None
    user.save(update_fields=['profile_picture'])
    transaction.on_commit(lambda: storage.delete(old))
