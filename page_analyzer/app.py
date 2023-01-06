from flask import (
    Flask,
    render_template,
    request,
    redirect,
    flash,
    url_for,
    abort)
from dotenv import load_dotenv
from urllib.parse import urlparse
from psycopg2.extras import NamedTupleCursor
from bs4 import BeautifulSoup
import os
import psycopg2
import datetime
import validators
import requests

app = Flask(__name__)
load_dotenv()
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
DATABASE_URL = os.getenv('DATABASE_URL')


@app.route('/')
def index():
    return render_template(
        'index.html'
    )


@app.post('/urls')
def add_url():
    url = request.form.to_dict()['url']
    if not validators.url(url):
        flash('Некорректный URL', 'danger')
        if not url:
            flash('URL обязателен', 'danger')
        elif not validators.length(url, max=255):
            flash('URL превышает 255 символов', 'danger')
        return render_template('index.html', url=url), 422
    normalized_url = normalize(url)
    connection = db_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute(
            "SELECT * FROM urls WHERE name=%s;",
            (normalized_url, )
        )
        existed_url = cursor.fetchone()
        if existed_url:
            flash('Страница уже существует', 'info')
            current_id = existed_url.id
        else:
            cursor.execute(
                "INSERT INTO urls (name, created_at) VALUES (%s, %s);",
                (normalized_url, datetime.datetime.now())
            )
            cursor.execute(
                "SELECT * FROM urls WHERE name=%s;",
                (normalized_url,)
            )
            added_url = cursor.fetchone()
            current_id = added_url.id
            flash('Страница успешно добавлена', 'success')
    connection.close()
    return redirect(url_for('get_url', id=current_id), 302)


@app.route('/urls/<int:id>')
def get_url(id):
    connection = db_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute("SELECT * FROM urls WHERE id=%s;", (id, ))
        url = cursor.fetchone()
        if not url:
            abort(404)
        cursor.execute(
            "SELECT * FROM url_checks WHERE url_id=%s ORDER BY id DESC;",
            (id,)
        )
        checks = cursor.fetchall()
    return render_template(
        'url.html',
        url=url,
        checks=checks
    )


@app.route('/urls')
def get_urls():
    connection = db_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute(
            '''
            SELECT DISTINCT ON (result_query.id) * FROM (
                SELECT urls.id, name, url_checks.created_at, status_code
                FROM url_checks
                RIGHT JOIN urls ON url_checks.url_id = urls.id
                ORDER BY urls.id DESC, url_checks.created_at DESC
            ) as result_query
            ORDER BY result_query.id DESC;
            '''
        )
        all_urls = cursor.fetchall()
    connection.close()
    return render_template(
        'urls.html',
        urls=all_urls
    )


@app.post('/urls/<int:id>/checks')
def check_url(id):
    connection = db_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute("SELECT * FROM urls WHERE id=%s;", (id, ))
        url = cursor.fetchone()
        response = http_request(url.name)
        if not response:
            flash('Произошла ошибка при проверке', 'danger')
        else:
            page_content = get_url_content(response)
            cursor.execute(
                '''
                INSERT INTO url_checks
                (url_id, created_at, status_code, h1, title, description)
                VALUES (%s, %s, %s, %s, %s, %s);
                ''',
                (
                    id,
                    datetime.datetime.now(),
                    response.status_code,
                    page_content['h1'],
                    page_content['title'],
                    page_content['description']
                )
            )
            flash('Страница успешно проверена', 'success')
    connection.close()
    return redirect(url_for('get_url', id=id), 302)


@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404


def db_connect():
    try:
        connection = psycopg2.connect(DATABASE_URL)
        connection.autocommit = True
        return connection
    except requests.exceptions.ConnectionError:
        return False


def http_request(url):
    try:
        response = requests.get(url)
        return response
    except requests.exceptions.ConnectionError:
        return False


def get_url_content(response):
    data = {
        'h1': '',
        'title': '',
        'description': ''
    }
    page = BeautifulSoup(response.text, 'html.parser')
    if page.find('h1'):
        data['h1'] = page.find('h1').text
    if page.find('title'):
        data['title'] = page.find('title').text
    description = page.find('meta', attrs={'name': 'description'})
    if description:
        data['description'] = description['content']
    return data


def normalize(url):
    url = urlparse(url)
    return f'{url.scheme}://{url.netloc}'
