from request import sogs_get, sogs_post
from sogs import crypto, config
from sogs.hashing import blake2b
from sogs.utils import encode_base64
from sogs.model.user import SystemUser
import nacl.bindings as salt
from nacl.utils import random
import time


def test_dm_default_empty(client, blind_user):
    r = sogs_get(client, '/inbox', blind_user)
    assert r.status_code == 200
    assert r.json == []


def test_dm_banned_user(client, banned_user):
    r = sogs_get(client, '/inbox', banned_user)
    assert r.status_code == 403


def make_post(message, sender, to):
    assert sender.is_blinded
    assert to.is_blinded
    a = sender.ed_key.to_curve25519_private_key().encode()
    kA = bytes.fromhex(sender.session_id[2:])
    kB = bytes.fromhex(to.session_id[2:])
    key = blake2b(salt.crypto_scalarmult_ed25519_noclamp(a, kB) + kA + kB, digest_size=32)

    # MESSAGE || UNBLINDED_ED_PUBKEY
    plaintext = message + sender.ed_key.verify_key.encode()
    nonce = random(24)
    ciphertext = salt.crypto_aead_xchacha20poly1305_ietf_encrypt(
            plaintext, aad=None, nonce=nonce, key=key)
    data = b'\x00' + ciphertext + nonce
    return {'message': encode_base64(data)}


def test_dm_send_from_banned_user(client, blind_user, blind_user2):
    blind_user2.ban(banned_by=SystemUser())
    r = sogs_post(
        client, f'/inbox/{blind_user.session_id}', make_post(b'beep', sender=blind_user2, to=blind_user), blind_user2
    )
    assert r.status_code == 403


def test_dm_send_to_banned_user(client, blind_user, blind_user2):
    blind_user2.ban(banned_by=SystemUser())
    r = sogs_post(
        client, f'/inbox/{blind_user2.session_id}', make_post(b'beep', sender=blind_user, to=blind_user2), blind_user
    )
    assert r.status_code == 404


def test_dm_send(client, blind_user, blind_user2):
    post = make_post(b'bep', sender=blind_user, to=blind_user2)
    r = sogs_post(client, f'/inbox/{blind_user2.session_id}', post, blind_user)
    assert r.status_code == 201
    r = sogs_get(client, '/inbox', blind_user2)
    assert r.status_code == 200
    assert len(r.json) == 1
    data = r.json[0]
    now = time.time()
    assert -1 < data.pop('posted_at') - time.time() < 1
    assert -1 < data.pop('expires_at') - config.DM_EXPIRY_DAYS*86400 - time.time() < 1
    assert data == {
            'id': 1,
            'message': post['message'],
            'sender': blind_user.session_id,
            }
