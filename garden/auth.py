import functools
import string
import random
import uuid

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, Response, jsonify
)

from werkzeug.security import check_password_hash, generate_password_hash

from garden.db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/register', methods=['POST'])
def register():
    if request.method == 'POST':
        nickname = request.form['nickname']
        db = get_db()
        error = None

        if not nickname:
            error = 'Nickname is required.'

        if error is None:

            identifier = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(255))
            secret = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(255))

            db.execute(
                'INSERT INTO client (uuid, identifier, secret, active, nickname) VALUES (?, ?, ?, ?, ?)',
                (str(uuid.uuid4()), identifier, generate_password_hash(secret), 0, nickname)
            )
            db.commit()

            output = {'identifier': identifier, 'secret': secret, 'nickname': nickname}

            return jsonify(output), 200 

        return jsonify(error=error), 400 
