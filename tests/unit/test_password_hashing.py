from app.core.security import hash_password, verify_password


def test_verify_password_accepts_the_correct_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)


def test_verify_password_rejects_a_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_hash_password_is_salted_and_nondeterministic() -> None:
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b
    assert verify_password("same password", a)
    assert verify_password("same password", b)


def test_verify_password_fails_closed_on_malformed_hash() -> None:
    assert not verify_password("anything", "not-a-real-bcrypt-hash")


def test_hash_password_handles_passwords_longer_than_bcrypts_72_byte_limit() -> None:
    long_password = "x" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)
    assert not verify_password("y" * 200, hashed)
