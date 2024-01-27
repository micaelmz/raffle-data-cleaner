from flask import Flask, render_template, request, jsonify, make_response, session, redirect, send_file, flash, \
    get_flashed_messages
import flask
import sqlalchemy
import pandas as pd
import json

app = Flask(__name__)
app.config["SECRET_KEY"] = "superscretekey"


def connect_to_db() -> sqlalchemy.engine.Connection:
    return sqlalchemy.create_engine(
        f'{session["db_engine"]}://{session["username"]}:{session["password"]}@{session["server_address"]}/{session["database_name"]}').connect()


def check_db_credentials(username: str, password: str, server_address: str, database_name: str,
                         db_engine: int) -> flask.Response:
    match db_engine:
        case 1:
            db_engine = 'mysql+pymysql'
        case 2:
            db_engine = 'postgresql'
        case _:
            db_engine = 'unknown'

    try:
        engine = sqlalchemy.create_engine(f'{db_engine}://{username}:{password}@{server_address}/{database_name}')
        connection = engine.connect()
        connection.execute(sqlalchemy.text('SHOW TABLES'))
        connection.close()

    except Exception as e:
        flash("Erro ao conectar ao banco de dados")
        flash(str(e))
        return redirect('/error')

    else:
        session['username'] = username
        session['password'] = password
        session['server_address'] = server_address
        session['db_engine'] = db_engine
        session['database_name'] = database_name
        return redirect('/tables')


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    server_address = request.form.get('server_address')
    db_engine = request.form.get('db_engine')
    database_name = request.form.get('database_name')

    if not username or not password or not server_address or not db_engine or not database_name or not db_engine.isdigit():
        flash("Preencha todos os campos")
        return redirect('/error')

    else:
        return check_db_credentials(username, password, server_address, database_name, int(db_engine))


@app.route('/error')
def error():
    message = get_flashed_messages()
    return render_template('error.html', errors=message)


@app.route('/tables')
def tables():
    if not session.get('username'):
        return redirect('/')

    try:
        conn = connect_to_db()
    except Exception as e:
        session.clear()
        flash("Erro ao conectar ao banco de dados")
        flash(str(e))
        return redirect('/error')

    tables_and_its_columns = {}

    tables_names = conn.execute(sqlalchemy.text('SHOW TABLES')).fetchall()

    for table in tables_names:
        table_name = table[0]  # table is a tuple
        columns = conn.execute(sqlalchemy.text(f'SHOW COLUMNS FROM {table_name}')).fetchall()
        tables_and_its_columns[table_name] = [column[0] for column in columns]
    return render_template('tables.html', tables_and_its_columns=tables_and_its_columns)


@app.route('/review_cleaning', methods=['GET', 'POST'])
def review_cleaning():
    if not session.get('username'):
        return redirect('/')

    table_name = request.form.get('table_name')
    column_name = request.form.get('column_name')

    if not table_name or not column_name:
        flash("Selecione uma tabela e uma coluna")
        return redirect('/error')

    try:
        conn = connect_to_db()
    except Exception as e:
        session.clear()
        flash("Erro ao conectar ao banco de dados")
        flash(str(e))
        return redirect('/error')

    # Variaveis de controle
    all_numbers = set()
    updated_column_with_unique_values = []
    rows_with_repeated_numbers = set()

    # Variaveis de log
    original_number_owner_dict = {}
    original_number_owner = []
    repeated_numbers_occurrence = []
    sql_statements = []

    # Carrega a tabela do banco de dados como um dataframe do pandas
    df = pd.read_sql(f'SELECT * FROM {table_name}', conn)

    # Itera sobre a coluna selecionada, onde cada linha é uma lista de valores
    for index, list_of_values in enumerate(df[column_name]):

        if type(list_of_values) == str:
            list_of_values = list_of_values.split(',')

        new_list = []

        # Itera sobre os valores da lista, e limpa os espaços e colchetes
        for value in list_of_values:
            value = value.replace(' ', '').replace('[', '').replace(']', '').replace("'", '')
            value = int(value)  # Converte o valor para inteiro

            # Caso seja um valor inédito
            if value not in all_numbers:
                all_numbers.add(value)  # Adiciona o valor ao set de números unicos
                new_list.append(value)  # Mantém o valor na lista
                original_number_owner_dict[value] = index + 1
                original_number_owner.append({
                    "numero": value,
                    "linha": index + 1
                })  # Registra no log o dono do número
            # Caso seja um valor repetido
            else:
                rows_with_repeated_numbers.add(index + 1)
                repeated_numbers_occurrence.append({
                    "linha_com_numero_repetido": index + 1,
                    "numero": value,
                    "linha_original_do_numero": original_number_owner_dict[value]
                })  # Registra no log a linha, o número e o dono do número
                # Ignora o valor repetido e não adiciona na lista
        updated_column_with_unique_values.append(
            new_list)  # Adiciona a lista dos numero unicos que o usuario tem na coluna

    for row in rows_with_repeated_numbers:
        sql_statements.append(f'UPDATE {table_name} SET {column_name} = "{updated_column_with_unique_values[row - 1]}" WHERE JSON_CONTAINS({column_name}, "{df[column_name][row - 1]}")')

    # Atualiza a coluna alvo da tabela com os valores unicos atualizados
    df[column_name] = updated_column_with_unique_values

    # Salva os dados de log em um arquivo json
    with open('log.json', 'w') as f:
        json.dump({
            "nome_da_tabela": table_name,
            "nome_da_coluna": column_name,
            "numeros_repetidos": {
                "total": len(repeated_numbers_occurrence),
                "ocorrencias": repeated_numbers_occurrence
            },
            "donos_originais_dos_numeros": original_number_owner,
            "sql_statements": sql_statements
        }, f)

    return render_template('confirmation.html',
                           table_name=table_name, column_name=column_name, count=len(repeated_numbers_occurrence),
                           matrix=df.to_numpy(), columns=df.columns.values.tolist(),
                           sql_statements="\n".join(sql_statements))


@app.route('/execute_sql', methods=['POST'])
def execute_sql():
    if not session.get('username'):
        return redirect('/')

    try:
        conn = connect_to_db()
    except Exception as e:
        session.clear()
        flash("Erro ao conectar ao banco de dados")
        flash(str(e))
        return redirect('/error')

    sql_statements = request.form.get('sql_statements').split('\n')

    rows_affected = 0
    try:
        for sql_statement in sql_statements:
            result = conn.execute(sqlalchemy.text(sql_statement))
            rows_affected += result.rowcount
        conn.commit()
    except Exception as e:
        flash("Erro ao executar os comandos SQL")
        flash(str(e))
        return redirect('/error')

    return render_template('success.html', rows_affected=rows_affected)


@app.route('/log')
def log():
    return send_file('log.json', as_attachment=(request.args.get('intent') == 'download'))


if __name__ == '__main__':
    app.run()
