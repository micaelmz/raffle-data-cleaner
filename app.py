from flask import Flask, render_template, request, jsonify, make_response, session, redirect, send_file
import sqlalchemy
import pandas as pd

app = Flask(__name__)
app.config["SECRET_KEY"] = "superscretekey"


def mysql_login(username, password, server_address, database_name):
    try:
        engine = sqlalchemy.create_engine(f'mysql+pymysql://{username}:{password}@{server_address}/{database_name}')
        connection = engine.connect()
        return connection
    except Exception as e:
        return str(e)


def postgres_login(username, password, server_address, database_name):
    try:
        engine = sqlalchemy.create_engine(f'postgresql://{username}:{password}@{server_address}/{database_name}')
        connection = engine.connect()
        return connection
    except Exception as e:
        return str(e)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/tables')
def tables():
    if not session.get('username'):
        return redirect('/')
    else:
        username = session['username']
        password = session['password']
        server_address = session['server_address']
        dialect = session['dialect']
        database_name = session['database_name']

        if dialect == '1':
            conn = mysql_login(username, password, server_address, database_name)
        else:
            conn = postgres_login(username, password, server_address, database_name)

        if not conn:
            return render_template("erro.html", error="Erro ao conectar ao banco de dados")
        else:
            tables_and_its_columns = {}
            tables = conn.execute(sqlalchemy.text('SHOW TABLES')).fetchall()
            for table in tables:
                table_name = table[0]
                columns = conn.execute(sqlalchemy.text(f'SHOW COLUMNS FROM {table_name}')).fetchall()
                tables_and_its_columns[table_name] = [column[0] for column in columns]
            return render_template('tables.html', tables_and_its_columns=tables_and_its_columns)


@app.route('/log')
def log():
    if not session.get('username'):
        return redirect('/')
    else:
        return send_file('log.json')

@app.route('/clean_table', methods=['GET', 'POST'])
def clean_table():
    if not session.get('username'):
        return redirect('/')
    else:
        username = session['username']
        password = session['password']
        server_address = session['server_address']
        dialect = session['dialect']
        database_name = session['database_name']

        if dialect == '1':
            conn = mysql_login(username, password, server_address, database_name)
        else:
            conn = postgres_login(username, password, server_address, database_name)

        if not conn:
            return render_template("erro.html", error="Erro ao conectar ao banco de dados")

        else:
            all_numbers = set()
            reapeated_numbers_count = 0
            updated_column_with_unique_values = []
            table_name = request.form.get('table_name')
            column_name = request.form.get('column_name')

            original_number_owner = {}
            rows_with_repeated_numbers = []

            if not table_name or not column_name:
                return render_template("erro.html", error="Preencha todos os campos")

            df = pd.read_sql(f'SELECT * FROM {table_name}', conn)

            for index, list_of_values in enumerate(df[column_name]):

                if type(list_of_values) == str:
                    list_of_values = list_of_values.split(',')

                new_list = []

                for value in list_of_values:
                    value = value.replace(' ', '').replace('[', '').replace(']', '').replace("'", '')
                    if value not in all_numbers:
                        all_numbers.add(value)
                        new_list.append(value)
                        original_number_owner[value] = index+1
                    else:
                        reapeated_numbers_count += 1
                        rows_with_repeated_numbers.append({
                            "linha": index+1,
                            "numero": value,
                            "dono_do_numero": original_number_owner[value]
                        })
                updated_column_with_unique_values.append(new_list)

            df[column_name] = updated_column_with_unique_values

            matrix = df.to_numpy()

            with open('log.json', 'w') as f:
                f.write(str(rows_with_repeated_numbers).replace("'", '"'))

            return render_template('confirmation.html',
                                   table_name=table_name, column_name=column_name, count=reapeated_numbers_count,
                                   matrix=matrix
                                   )


@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    server_address = request.form.get('server')
    dialect = request.form.get('sql-dialect')
    database_name = request.form.get('database')

    if not username or not password or not server_address or not dialect or not database_name:
        return render_template("erro.html", error="Preencha todos os campos")

    if dialect == '1':
        conn = mysql_login(username, password, server_address, database_name)
    else:
        conn = postgres_login(username, password, server_address, database_name)

    if type(conn) == str:
        return render_template("erro.html", error="Erro ao conectar ao banco de dados\n" + conn)
    else:
        session['username'] = username
        session['password'] = password
        session['server_address'] = server_address
        session['dialect'] = dialect
        session['database_name'] = database_name
        return redirect('/tables')


if __name__ == '__main__':
    app.run()
