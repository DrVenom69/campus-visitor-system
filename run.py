from app import create_app

app = create_app()

if __name__ == "__main__":
    # Development server only. Never run with debug=True on a public server.
    app.run(debug=True)
