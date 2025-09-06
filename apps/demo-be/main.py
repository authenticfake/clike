from fastapi import FastAPI
app=FastAPI()
@app.get('/api/hello')
def hello():
    return {'msg':'hello from demo-be'}
