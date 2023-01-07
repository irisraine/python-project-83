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
    return render_template('index.html')


@app.route('/urls')
def get_urls():
    connection = database_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute(
            '''
            SELECT DISTINCT ON (urls.id)
                urls.id, name, url_checks.created_at, status_code
            FROM url_checks RIGHT JOIN urls ON url_checks.url_id = urls.id
            ORDER BY urls.id DESC, url_checks.created_at DESC;
            '''
        )
        urls = cursor.fetchall()
    connection.close()
    return render_template('urls.html', urls=urls)


@app.route('/urls/<int:id>')
def get_url(id):
    connection = database_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute(
            "SELECT * FROM urls WHERE id=%s;",
            (id, )
        )
        url = cursor.fetchone()
        if not url:
            abort(404)
        cursor.execute(
            "SELECT * FROM url_checks WHERE url_id=%s ORDER BY id DESC;",
            (id, )
        )
        checks = cursor.fetchall()
    connection.close()
    return render_template('url.html', url=url, checks=checks)


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
    connection = database_connect()
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
                (normalized_url, )
            )
            added_url = cursor.fetchone()
            current_id = added_url.id
            flash('Страница успешно добавлена', 'success')
    connection.close()
    return redirect(url_for('get_url', id=current_id), 302)


@app.post('/urls/<int:id>/checks')
def check_url(id):
    connection = database_connect()
    with connection.cursor(cursor_factory=NamedTupleCursor) as cursor:
        cursor.execute(
            "SELECT * FROM urls WHERE id=%s;",
            (id, )
        )
        url = cursor.fetchone()
        site_content = get_site_content(url.name)
        if not site_content:
            flash('Произошла ошибка при проверке', 'danger')
        else:
            cursor.execute(
                '''
                INSERT INTO url_checks
                (url_id, created_at, status_code, h1, title, description)
                VALUES (%s, %s, %s, %s, %s, %s);
                ''',
                (
                    id,
                    datetime.datetime.now(),
                    site_content['status_code'],
                    site_content['h1'],
                    site_content['title'],
                    site_content['description']
                )
            )
            flash('Страница успешно проверена', 'success')
    connection.close()
    return redirect(url_for('get_url', id=id), 302)


@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404


@app.template_filter()
def format_timestamp(datetime):
    return datetime.strftime('%Y-%m-%d %H:%M:%S') if datetime else ''


def database_connect():
    try:
        connection = psycopg2.connect(DATABASE_URL)
        connection.autocommit = True
        return connection
    except psycopg2.DatabaseError or psycopg2.OperationalError:
        return False


def normalize(url):
    url = urlparse(url)
    return f'{url.scheme}://{url.netloc}'


def get_site_content(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        page = BeautifulSoup(response.text, 'html.parser')
        description = page.find('meta', attrs={'name': 'description'})
        site_content = {
            'status_code':
                response.status_code,
            'h1':
                page.find('h1').text if page.find('h1') else '',
            'title':
                page.find('title').text if page.find('title') else '',
            'description':
                description['content'] if description else ''
        }
        return site_content
    except requests.exceptions.RequestException:
        return False
