# apps/iris/iris_model.py
# 모델 준비 (최초 1회 실행)
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression
import pickle

iris = load_iris()
model = LogisticRegression(max_iter=200)
model.fit(iris.data, iris.target)
with open('apps/iris_sk_user/model.pkl', 'wb') as f:
    pickle.dump(model, f)
