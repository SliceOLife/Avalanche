# all the imports
from uuid import uuid4
from datetime import datetime
from base64 import b64encode
from os import urandom
import sys

import os
from flask import Flask, request, session, redirect, url_for, \
    abort, render_template, flash, make_response, jsonify, send_from_directory, \
    g
from flask.ext.httpauth import HTTPBasicAuth
from flask.ext.sqlalchemy import SQLAlchemy
from passlib.apps import custom_app_context as pwd_context

# init config
app = Flask(__name__)
app.config['USERNAME'] = 'dev'
app.config['PASSWORD'] = 'default'
app.config['SECRET_KEY'] = 'the quick brown fox jumps over the lazy dog'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['UPLOAD_FOLDER'] = 'uploads/source/'

# extra config
ALLOWED_EXTENSIONS = {'zip'}


# Extensions and such
auth = HTTPBasicAuth()
db = SQLAlchemy(app)
app.config.from_object(__name__)


class Entry(db.Model):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(32))
    text = db.Column(db.Text())
    lang = db.Column(db.String(32))
    user = db.Column(db.String(32))
    date = db.Column(db.String(32))
    uniqueid = db.Column(db.String(100))
    fileloc = db.Column(db.String(100))
    isactive = db.Column(db.Integer)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True)
    password_hash = db.Column(db.String(128))
    email = db.Column(db.String(120), unique=True)
    nickname = db.Column(db.String(32))
    total_problems = db.Column(db.Integer)
    api_id = db.Column(db.String(32))

    def hash_password(self, password):
      self.password_hash = pwd_context.encrypt(password)

    def verify_password(self, password):
      return pwd_context.verify(password, self.password_hash)

    def generate_api_id(self):
      self.api_id = b64encode(urandom(9))



# utils and such
def is_empty(any_structure):
    if any_structure:
        return False
    else:
        return True


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


@app.route('/')
def show_entries():
    if not session.get('logged_in'):
      return render_template('reg_new.html')
    else:
      return render_template('post_new.html')


@app.route('/add', methods=['POST'])
def add_entry():
    i = datetime.now()
    if not session.get('logged_in'):
        abort(401)

    if request.form['title'] is None or request.form['text'] is None or request.form['lang'] is None or request.form[
        'user'] is None:
        flash('Onvoldoende gegevens ingevuld, probeer het opnieuw.')
        return redirect(url_for('show_entries'))
    else:
        file = request.files['file']
        uniqueid = str(uuid4())
        if file and allowed_file(file.filename):
            filename = 'source_' + uniqueid + '.' + file.filename.rsplit('.', 1)[1]
            fPath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(fPath)
            fileLoc = '/uploads/source/' + filename
        else:
            fileLoc = ""
            #return redirect(url_for('show_entries'))
        entry = Entry(title=request.form['title'], text=request.form['text'], lang=request.form['lang'],
                      user=request.form['user'], date=str(i.strftime('%Y/%m/%d %H:%M:%S')), uniqueid=uniqueid,
                      fileloc=fileLoc, isactive=1)
        db.session.add(entry)
        db.session.commit()
        #flash(
        #'Bedankt voor het posten van uw probleem! Bewaar de volgende reeks goed om uw probleem te kunnen bewerken: ' + entry.uniqueid)
        return render_template('post_success.html',
                               success='Bedankt voor het posten van uw probleem! Bewaar de volgende reeks goed om uw probleem te kunnen bewerken: ' + entry.uniqueid)

@app.route('/register', methods=['POST'])
def add_user():
  i = datetime.now()
  if session.get('logged_in'):
    flash('U bent al geregistreerd!')
    return redirect(url_for('show_entries'))
  else:
    username = request.form['username']
    password = request.form['password']
    email = request.form['email']
    nickname = request.form['nickname']
    if username is None or password is None:
        abort(400)    # missing arguments
    if User.query.filter_by(username=username).first() is not None:
        abort(400)    # existing user
    user = User(username=username,email=email,nickname=nickname)
    user.hash_password(password)
    user.generate_api_id()
    db.session.add(user)
    db.session.commit()
    return render_template('profile.html', user=user)


@app.route('/login', methods=['GET', 'POST'])
def login():
  username = request.form['username']
  password = request.form['password']
  error = None

  if request.method == 'POST':
    user = User.query.filter_by(username=username).first()
    if not user or not user.verify_password(password):
      error = 'Foutieve gebruikersnaam en of wachtwoord!'
      return render_template('index_new.html', error=error)
    g.user = user
    session['logged_in'] = True
    flash('U bent succesvol ingelogd')
    return redirect(url_for('show_entries'))


@app.route('/exp')
def show_entries_exp():
    entries = Entry.query.all()
    return render_template('show_entries_exp.html', entries=entries)


@app.route('/exp_p')
def post_entry_exp():
    return render_template('post_new.html')


@app.route('/projector')
def show_entries_projector():
    entries = Entry.query.all()
    return render_template('show_entries_projector.html', entries=entries)


@app.route('/profile')
def show_profile():
    return render_template('profile.html')


@app.route('/indexn')
def show_indexn():
    return render_template('index_new.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash("U bent succesvol uitgelogd")
    return redirect(url_for('show_entries'))


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# API routing ( CRUD )

@app.route('/api/users', methods=['POST'])
def new_user():
    username = request.json.get('username')
    password = request.json.get('password')
    if username is None or password is None:
        abort(400)  # missing arguments
    if User.query.filter_by(username=username).first() is not None:
        abort(400)  # existing user
    user = User(username=username)
    user.hash_password(password)
    user.generate_api_id()
    db.session.add(user)
    db.session.commit()
    return jsonify({'username': user.username}), 201, {'Location': url_for('get_user', id=user.id, _external=True)}


# Public API method. Gets list of all current issues in tracker.
@app.route('/api/v1.0/issues/', methods=['GET'])
def show_entries_api():
    cols = ['id', 'title', 'text', 'lang', 'user', 'date', 'fileloc', 'isactive']
    data = Entry.query.all()
    issue = [{col: getattr(d, col) for col in cols} for d in data]

    if is_empty(issue):
        response = jsonify({'error': 'no issues'})
        response.status_code = 404
        return response
    else:
        return jsonify(issues=issue)


# Public API method. Get specific issue by ID
@app.route('/api/v1.0/issues/<int:api_id>', methods=['GET'])
def show_entry_api(api_id):
    cols = ['title', 'text', 'lang', 'user', 'date', 'fileloc', 'isactive']
    data = Entry.query.filter(Entry.id == api_id).all()
    issue = [{col: getattr(d, col) for col in cols} for d in data]

    if is_empty(issue):
        response = jsonify({'error': 'issue not found'})
        response.status_code = 404
        return response
    else:
        return jsonify(issue=issue)


# Public API method. Post a new issue to tracker.
# TODO: Look into file upload using post.
@app.route('/api/v1.0/issues/post', methods=['POST'])
def post_entry_api():
    title = request.json.get('title')
    text = request.json.get('text')
    lang = request.json.get('lang')
    user = request.json.get('user')
    date = datetime.now()
    uniqueid = uuid4()
    if title is None or text is None:
        abort(400)  # missing arguments

    entry = Entry(title=title, text=text, lang=lang, user=user, date=str(date.strftime('%Y/%m/%d %H:%M:%S')),
                  uniqueid=str(uniqueid))
    db.session.add(entry)
    db.session.commit()

    response = jsonify({'success': 'true', 'uuid': entry.uniqueid})
    response.status_code = 201
    return response


# Private API method. Modify issue by unique ID assigned on issue creation
@app.route('/api/v1.0/issues/update', methods=['POST'])
def update_entry_api():
    utitle = request.json.get('title')
    utext = request.json.get('text')
    ulang = request.json.get('lang')
    uuser = request.json.get('user')
    udate = datetime.now()
    uuniqueid = request.json.get('uniqueid')
    if utitle is None or utext is None or uuniqueid is None:
        abort(400)  # missing args

    issue = Entry.query.filter(Entry.uniqueid == uuniqueid).first()

    if is_empty(issue):
        response = jsonify({'error': 'unknown issue'})
        response.status_code = 404
        return response
    else:
        issue.title = utitle
        issue.text = utext
        issue.lang = ulang
        issue.user = uuser
        issue.date = udate
        db.session.commit()

        response = jsonify({'success': 'true', 'uuid': uuniqueid})
        response.status_code = 200
        return response


# Private API method. Mark issue inactive by unique ID assigned on issue creation
@app.route('/api/v1.0/issues/deactivate', methods=['POST'])
def inactive_entry_api():
    uniqueid = request.json.get('uniqueid')
    if uniqueid is None:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)

    issue = Entry.query.filter(Entry.uniqueid == uniqueid).first()

    if is_empty(issue):
        response = jsonify({'error': 'unknown issue'})
        response.status_code = 404
        return response
    else:
        issue.isactive = 0
        db.session.commit()

        response = jsonify({'success': 'true', 'uuid': uniqueid})
        response.status_code = 200
        return response


# Private API method. Mark issue active by unique ID assigned on issue creation
@app.route('/api/v1.0/issues/activate', methods=['POST'])
def active_entry_api():
    uniqueid = request.json.get('uniqueid')
    if uniqueid is None:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)

    issue = Entry.query.filter(Entry.uniqueid == uniqueid).first()

    if is_empty(issue):
        response = jsonify({'error': 'unknown issue'})
        response.status_code = 404
        return response
    else:
        issue.isactive = 1
        db.session.commit()

        response = jsonify({'success': 'true', 'uuid': uniqueid})
        response.status_code = 200
        return response


# Private API method. Delete issue by unique ID assigned on issue creation
@app.route('/api/v1.0/issues/delete', methods=['POST'])
def delete_entry_api():
    uniqueid = request.json.get('uniqueid')
    if uniqueid is None:
        return make_response(jsonify({'error': 'Invalid arguments'}), 400)

    issue = Entry.query.filter(Entry.uniqueid == uniqueid).first()

    if is_empty(issue):
        response = jsonify({'error': 'unknown issue'})
        response.status_code = 404
        return response
    else:
        db.session.delete(issue)
        db.session.commit()

        # We need to kill the corresponding source files too if they exist
        sourcefile = os.path.dirname(os.path.realpath(sys.argv[0])) + issue.fileloc
        if os.path.isfile(sourcefile):
            os.remove(sourcefile)
        else:
            response = jsonify({'success': 'false', 'fileloc_del': sourcefile})
            response.status_code = 500
            return response
        response = jsonify({'success': 'true'})
        response.status_code = 200
        return response


if __name__ == '__main__':
    if not os.path.exists('db.sqlite'):
        db.create_all()
    app.run(host='0.0.0.0', debug=True)
