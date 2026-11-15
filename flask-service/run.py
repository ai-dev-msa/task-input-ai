from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000, # ini harusnya 5000 ya bukan 5001 //notes
        debug=False # ini harusnya False jangan True biar bisa langsung jalan pas eror //notes
        )