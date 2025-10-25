from flask import Flask, request, redirect, render_template, url_for, flash, session, send_file
import sqlite3
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = 'Unaclavesecreta'


# ========================
# Inicializar la base de datos
# ========================
def init_database():
    conn = sqlite3.connect('sist_evaluacion.db')
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            correo TEXT NOT NULL UNIQUE,
            rol TEXT NOT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS encuestas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            fecha_creacion TEXT NOT NULL,
            id_usuario INTEGER,
            FOREIGN KEY (id_usuario) REFERENCES usuarios(id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preguntas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_encuesta INTEGER NOT NULL,
            texto_pregunta TEXT NOT NULL,
            tipo TEXT NOT NULL,
            FOREIGN KEY (id_encuesta) REFERENCES encuestas(id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS respuestas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_pregunta INTEGER NOT NULL,
            id_usuario INTEGER NOT NULL,
            respuesta_texto TEXT NOT NULL,
            valor TEXT NOT NULL,
            FOREIGN KEY (id_pregunta) REFERENCES preguntas(id),
            FOREIGN KEY (id_usuario) REFERENCES usuarios(id)
        );
    """)

    conn.commit()
    conn.close()


init_database()


# ========================
# Función de conexión
# ========================
def get_db_connection():
    conn = sqlite3.connect("sist_evaluacion.db")
    conn.row_factory = sqlite3.Row
    return conn


# ========================
# LOGIN Y USUARIOS
# ========================
@app.route("/")
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nombre = request.form["nombre"].strip()
        correo = request.form["correo"].strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE nombre=? AND correo=?", (nombre, correo))
        usuario = cursor.fetchone()
        conn.close()

        if usuario:
            session["usuario_id"] = usuario["id"]
            session["nombre"] = usuario["nombre"]
            flash(f"Bienvenido {usuario['nombre']}")
            return redirect(url_for("index"))
        else:
            flash("Usuario no encontrado. Cree una cuenta.")
            return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/usuario", methods=["GET", "POST"])
def crear_usuario():
    if request.method == "POST":
        nombre = request.form["nombre"]
        correo = request.form["correo"]
        rol = "usuario"

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO usuarios (nombre, correo, rol) VALUES (?, ?, ?)",
                        (nombre, correo, rol))
            conn.commit()
            flash("Cuenta creada correctamente. Ahora inicia sesión.")
        except sqlite3.IntegrityError:
            flash("Ese correo ya está registrado.")
        conn.close()
        return redirect(url_for("login"))
    return render_template("usuario.html")


# ========================
# INDEX — Ver encuestas
# ========================
@app.route("/index")
def index():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    encuestas = conn.execute("SELECT * FROM encuestas").fetchall()
    conn.close()

    return render_template("index.html", nombre=session["nombre"], encuestas=encuestas)


# ========================
# CREAR NUEVA ENCUESTA
# ========================
@app.route("/crear_encuesta", methods=["GET", "POST"])
def crear_encuesta():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        titulo = request.form["titulo"]
        descripcion = request.form["descripcion"]
        cantidad = int(request.form["cantidad"])

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO encuestas (titulo, descripcion, fecha_creacion, id_usuario) VALUES (?, ?, ?, ?)",
                    (titulo, descripcion, fecha, session["usuario_id"]))
        id_encuesta = cursor.lastrowid

        # Insertar preguntas
        for i in range(1, cantidad + 1):
            pregunta = request.form[f"pregunta_{i}"]
            tipo = request.form[f"tipo_{i}"]
            cursor.execute("INSERT INTO preguntas (id_encuesta, texto_pregunta, tipo) VALUES (?, ?, ?)",
                        (id_encuesta, pregunta, tipo))

        conn.commit()
        conn.close()
        flash("Encuesta creada correctamente.")
        return redirect(url_for("index"))

    return render_template("crear_encuesta.html")


# ========================
# LLENAR ENCUESTA
# ========================
@app.route("/llenar_encuesta/<int:id_encuesta>", methods=["GET", "POST"])
def llenar_encuesta(id_encuesta):
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    encuesta = conn.execute("SELECT * FROM encuestas WHERE id=?", (id_encuesta,)).fetchone()
    preguntas = conn.execute("SELECT * FROM preguntas WHERE id_encuesta=?", (id_encuesta,)).fetchall()

    if request.method == "POST":
        for p in preguntas:
            respuesta = request.form.get(f"respuesta_{p['id']}")
            conn.execute("INSERT INTO respuestas (id_pregunta, id_usuario, respuesta_texto, valor) VALUES (?, ?, ?, ?)",
                        (p["id"], session["usuario_id"], respuesta, respuesta))
        conn.commit()
        conn.close()
        flash("Encuesta completada exitosamente.")
        return redirect(url_for("index"))

    conn.close()
    return render_template("llenar_encuesta.html", encuesta=encuesta, preguntas=preguntas)

# ========================
# VER RESULTADOS
# ========================
@app.route("/resultados/<int:id_encuesta>")
def resultados(id_encuesta):
    conn = get_db_connection()
    encuesta = conn.execute("SELECT * FROM encuestas WHERE id=?", (id_encuesta,)).fetchone()
    preguntas = conn.execute("SELECT * FROM preguntas WHERE id_encuesta=?", (id_encuesta,)).fetchall()

    # Categorías fijas
    categorias = ["si", "no", "satisfecho", "insatisfecho", "acuerdo", "desacuerdo", "neutral"]

    datos = []
    for p in preguntas:
        conteos = {cat: 0 for cat in categorias}

        respuestas = conn.execute("""
            SELECT respuesta_texto, COUNT(*) as total
            FROM respuestas
            WHERE id_pregunta = ?
            GROUP BY respuesta_texto
        """, (p["id"],)).fetchall()

        total_respuestas = sum(r["total"] for r in respuestas)
        if total_respuestas > 0:
            for r in respuestas:
                resp = r["respuesta_texto"].lower().strip()
                if resp in conteos:
                    conteos[resp] = round((r["total"] / total_respuestas) * 100, 2)

        datos.append({"pregunta": p["texto_pregunta"], "porcentajes": conteos})

    conn.close()
    return render_template("resultados.html", encuesta=encuesta, datos=datos)


# ========================
# EXPORTAR RESULTADOS A PDF
# ========================
@app.route("/exportar_pdf/<int:id_encuesta>")
def exportar_pdf(id_encuesta):
    conn = get_db_connection()
    encuesta = conn.execute("SELECT * FROM encuestas WHERE id=?", (id_encuesta,)).fetchone()
    preguntas = conn.execute("SELECT * FROM preguntas WHERE id_encuesta=?", (id_encuesta,)).fetchall()

    categorias = ["si", "no", "satisfecho", "insatisfecho", "acuerdo", "desacuerdo", "neutral"]

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, f"Título: {encuesta['titulo']}")
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 70, f"Descripción: {encuesta['descripcion']}")
    c.drawString(50, height - 90, f"Fecha de creación: {encuesta['fecha_creacion']}")
    y = height - 120

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Respuestas en porcentajes:")
    y -= 20

    for p in preguntas:
        # Obtener respuestas para esta pregunta
        conteos = {cat: 0 for cat in categorias}
        respuestas = conn.execute("""
            SELECT respuesta_texto, COUNT(*) as total
            FROM respuestas
            WHERE id_pregunta = ?
            GROUP BY respuesta_texto
        """, (p["id"],)).fetchall()
        total_respuestas = sum(r["total"] for r in respuestas)
        if total_respuestas > 0:
            for r in respuestas:
                resp = r["respuesta_texto"].lower().strip()
                if resp in conteos:
                    conteos[resp] = round((r["total"] / total_respuestas) * 100, 2)

        if y < 100:
            c.showPage()
            y = height - 50

        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, f"Pregunta: {p['texto_pregunta']}")
        y -= 15
        c.setFont("Helvetica", 10)
        linea = " | ".join([f"{cat.capitalize()}: {valor}%" for cat, valor in conteos.items()])
        c.drawString(60, y, linea)
        y -= 25

    conn.close()
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="resultados.pdf", mimetype="application/pdf")



# ========================
# ELIMINAR ENCUESTA (con validación y alerta)
# ========================
@app.route("/eliminar_encuesta/<int:id_encuesta>")
def eliminar_encuesta(id_encuesta):
    # 1️⃣ Verificar que el usuario haya iniciado sesión
    if "usuario_id" not in session:
        flash("Debes iniciar sesión para eliminar encuestas.")
        return redirect(url_for("login"))

    conn = get_db_connection()
    encuesta = conn.execute("SELECT * FROM encuestas WHERE id=?", (id_encuesta,)).fetchone()

    # 2️⃣ Validar que la encuesta exista
    if not encuesta:
        flash("La encuesta no existe.")
        conn.close()
        return redirect(url_for("index"))

    # 3️⃣ Validar si el usuario actual es el creador
    if encuesta["id_usuario"] != session["usuario_id"]:
        flash("No puedes eliminar esta encuesta porque no la creaste.")
        conn.close()
        return redirect(url_for("index"))

    # 4️⃣ Si es el creador, eliminar la encuesta
    conn.execute("DELETE FROM encuestas WHERE id=?", (id_encuesta,))
    conn.commit()
    conn.close()

    flash("Encuesta eliminada exitosamente.")
    return redirect(url_for("index"))



# ========================
# LOGOUT
# ========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
