"""UserPhotos upload size limit."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from profiles.serializers import UserPhotosSerializer, _PHOTO_SIZE_ERROR


class UserPhotosSerializerSizeTests(SimpleTestCase):
    def test_rejects_file_over_2mb(self):
        payload = b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024)
        upload = SimpleUploadedFile("photo.jpg", payload, content_type="image/jpeg")
        ser = UserPhotosSerializer(data={"profile_photo": upload})
        self.assertFalse(ser.is_valid())
        self.assertIn("profile_photo", ser.errors)
        self.assertIn(_PHOTO_SIZE_ERROR, str(ser.errors["profile_photo"]))
