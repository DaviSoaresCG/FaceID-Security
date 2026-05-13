import base64 #para codificação de imagem
import os
import sqlite3
import pickle #para serialização de objetos e salvar o rosto no banco de dados
from flask import Flask, render_template, request, redirect, url_for, jsonify
import cv2 #para processamento de imagem
import face_recognition 
import numpy as np

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
DB = 'database.db'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pessoas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            cpf TEXT,
            data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS imagens(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pessoa_id INTEGER,
            caminho_imagem TEXT,
            encoding BLOB
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    conn = get_db()
    total_pessoas = conn.execute("SELECT COUNT(*) FROM pessoas").fetchone()[0]
    total_imagens = conn.execute("SELECT COUNT(*) FROM imagens").fetchone()[0]
    conn.close()
    return render_template('index.html', total_pessoas=total_pessoas, total_imagens=total_imagens)

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form['nome']
        cpf = request.form['cpf']
        files = request.files.getlist('foto')

        if not files or files[0].filename == '':
            return render_template('cadastro.html', erro="Nenhuma imagem enviada.")

        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO pessoas(nome, cpf) VALUES(?, ?)", (nome, cpf))
        pessoa_id = cur.lastrowid
        
        rostos_salvos = 0

        for file in files:
            if file.filename == '':
                continue
                
            path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(path)

            image = face_recognition.load_image_file(path)
            faces = face_recognition.face_encodings(image)

            if len(faces) == 0:
                os.remove(path)
                continue # Skip images without faces
            
            face_encoding = faces[0]
            encoding_bytes = pickle.dumps(face_encoding)

            cur.execute("INSERT INTO imagens(pessoa_id, caminho_imagem, encoding) VALUES(?, ?, ?)",
                        (pessoa_id, path, encoding_bytes))
            rostos_salvos += 1

        if rostos_salvos == 0:
            # Revert person creation if no faces were found in any image
            cur.execute("DELETE FROM pessoas WHERE id = ?", (pessoa_id,))
            conn.commit()
            conn.close()
            return render_template('cadastro.html', erro="Nenhum rosto detectado nas imagens enviadas. Tente novamente.")

        conn.commit()
        conn.close()

        return redirect(url_for('lista'))
    
    return render_template('cadastro.html')

@app.route('/lista')
def lista():
    conn = get_db()
    pessoas = conn.execute("SELECT * FROM pessoas ORDER BY id DESC").fetchall()
    conn.close()
    return render_template('lista.html', pessoas=pessoas)

@app.route('/deletar/<int:id>', methods=['POST'])
def deletar(id):
    conn = get_db()
    
    # Get images to delete from filesystem
    imagens = conn.execute("SELECT caminho_imagem FROM imagens WHERE pessoa_id = ?", (id,)).fetchall()
    for img in imagens:
        try:
            if os.path.exists(img['caminho_imagem']):
                os.remove(img['caminho_imagem'])
        except Exception as e:
            print(f"Error removing file {img['caminho_imagem']}: {e}")
            
    # Delete from database
    conn.execute("DELETE FROM imagens WHERE pessoa_id = ?", (id,))
    conn.execute("DELETE FROM pessoas WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('lista'))

def get_known_encodings():
    conn = get_db()
    # Join to get the person's name
    query = """
        SELECT i.encoding, p.id, p.nome 
        FROM imagens i
        JOIN pessoas p ON i.pessoa_id = p.id
        WHERE i.encoding IS NOT NULL
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    encodings = []
    ids = []
    nomes = []

    for row in rows:
        if row['encoding']:
            encodings.append(pickle.loads(row['encoding']))
            ids.append(row['id'])
            nomes.append(row['nome'])

    return encodings, ids, nomes

@app.route('/reconhecer/webcam', methods=['GET'])
def reconhecer_webcam():
    return render_template('reconhecer_webcam.html')

@app.route('/reconhecer/imagem', methods=['GET'])
def reconhecer_imagem_page():
    return render_template('reconhecer_imagem.html')

@app.route('/api/reconhecer', methods=['POST'])
def api_reconhecer():
    data = request.json
    if not data or 'image' not in data:
        return jsonify({"erro": "Nenhuma imagem recebida"}), 400
    
    # Process base64 image
    base64_data = data['image']
    if "," in base64_data:
        base64_data = base64_data.split(",")[1]
    
    img_bytes = base64.b64decode(base64_data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        return jsonify({"erro": "Falha ao decodificar imagem"}), 400

    # Convert to RGB for face_recognition
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    face_locations = face_recognition.face_locations(rgb_frame)
    face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

    known_encodings, known_ids, known_nomes = get_known_encodings()

    resultados_finais = []

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        name = "Desconhecido"
        pessoa_id = None
        confianca = 0.0

        if known_encodings:
            face_distances = face_recognition.face_distance(known_encodings, face_encoding)
            best_match_index = np.argmin(face_distances)
            if face_distances[best_match_index] < 0.6: # Distance threshold
                pessoa_id = known_ids[best_match_index]
                name = known_nomes[best_match_index]
                # Convert distance to confidence %
                dist = face_distances[best_match_index]
                # Simulating a percentage where 0 distance = 100%, 0.6 distance = 40% (approx)
                confianca = round((1 - dist) * 100, 2)

        resultados_finais.append({
            "box": {"top": top, "right": right, "bottom": bottom, "left": left},
            "nome": name,
            "id": pessoa_id,
            "confianca": f"{confianca}%" if pessoa_id else "N/A"
        })

    return jsonify({"rostos": resultados_finais})

@app.route('/api/reconhecer_upload', methods=['POST'])
def api_reconhecer_upload():
    if 'foto' not in request.files:
        return jsonify({"erro": "Nenhuma imagem enviada."}), 400
        
    file = request.files['foto']
    if file.filename == '':
        return jsonify({"erro": "Arquivo inválido."}), 400

    path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(path)

    image = face_recognition.load_image_file(path)
    face_locations = face_recognition.face_locations(image)
    face_encodings = face_recognition.face_encodings(image, face_locations)
    
    known_encodings, known_ids, known_nomes = get_known_encodings()

    resultados_finais = []

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        name = "Desconhecido"
        pessoa_id = None
        confianca = 0.0

        if known_encodings:
            face_distances = face_recognition.face_distance(known_encodings, face_encoding)
            best_match_index = np.argmin(face_distances)
            if face_distances[best_match_index] < 0.6:
                pessoa_id = known_ids[best_match_index]
                name = known_nomes[best_match_index]
                confianca = round((1 - face_distances[best_match_index]) * 100, 2)

        resultados_finais.append({
            "box": {"top": top, "right": right, "bottom": bottom, "left": left},
            "nome": name,
            "id": pessoa_id,
            "confianca": f"{confianca}%" if pessoa_id else "N/A"
        })

    os.remove(path) # Cleanup
    return jsonify({"rostos": resultados_finais})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
