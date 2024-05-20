# vim : set et ts=2 sw=2 :
"""
ez: ai can be easy, let me show you how   
(c) 2023, Tim Menzies, <timm@ieee.org>, BSD-2  
  
USAGE:    
1. download ez.py, etc.py, eg.py    
2. python3 eg.py [OPTIONS]   
  
OPTIONS:  

     -a --adequate    good if over adequate*best = .1
     -A --ample       only want this many rules  = 20
     -b --budget0     initial evals              = 4  
     -B --Budget      subsequent evals           = 5   
     -c --cohen       small effect size          = .35  
     -C --confidence  statistical confidence     = .05
     -d --diffTh      SNEAK: num diff threshold  = .25
     -e --effectSize  non-parametric small delta = 0.2385
     -E --Experiments number of Bootstraps       = 256
     -f --file        csv data file name         = '../data/SS-C.csv'  
     -F --Far         far search outlier control = .95 
     -h --help        print help                 = false
     -H --Half        #items for far search      = 256
     -k --k           rare class  kludge         = 1  
     -m --m           rare attribute  kludge     = 2  
     -M --Min         min size is N**Min         = .5
     -p --p           distance coefficient       = 2
     -r --ranges      max number of bins         = 16
     -R --Repeats     number of repeats          = 20
     -s --seed        random number seed         = 31210 
     -S --score       support exponent for range = 2  
     -t --todo        start up action            = 'help'   
     -T --Top         best section               = .5 
     -u --upper       in SMO, keep upper ratio   = .8  
"""

import re,sys,math,random
from collections import Counter
from stats import sk
from etc import o,isa,struct,merges
import etc
from math import pi
import numpy as np
from operator import xor




the = etc.THE(__doc__)
tiny= sys.float_info.min 

#          _   _   |   _ 
#         (_  (_)  |  _>                       

def isGoal(s):   return s[-1] in "+-!"
def isHeaven(s): return 0 if s[-1] == "-" else 1
def isNum(s):    return s[0].isupper() 

class SYM(Counter):
  "Adds `add` to Counter"
  def add(self,x,n=1): self[x] += n

  def entropy(self): 
    n = sum(self.values()) 
    return -sum(v/n*math.log(v/n,2) for _,v in self.items() if v>0)
  
  def __add__(i,j):
    k=SYM()
    [k.add(x,n) for old in [i,j] for x,n in old.items()]
    return k
  
class NUM(struct):
  def __init__(self,lst=[],txt=" "):
   self.n, self.mu, self.m2, self.sd, self.txt = 0,0,0,0,txt 
   self.lo, self.hi = sys.maxsize, -sys.maxsize
   self.heaven = isHeaven(txt)
   [self.add(x) for x in lst]

  def add(self,x):
    self.lo = min(x,self.lo)
    self.hi = max(x,self.hi)
    self.n += 1
    delta = x - self.mu
    self.mu += delta / self.n
    self.m2 += delta * (x -  self.mu)
    self.sd = 0 if self.n < 2 else (self.m2 / (self.n - 1))**.5

  def norm(self,x):
    return x=="?" and x or (x - self.lo) / (self.hi - self.lo + tiny)
 
#         ._   _          _ 
#         |   (_)  \/\/  _> 

class DATA(struct):
  def __init__(self, lsts=[], order=False):
    self.names,*rows = list(lsts) 
    self.rows = []
    self.cols = [(NUM(txt=s) if isNum(s) else SYM()) for s in self.names] 
    self.ys   = {n:c for n,(s,c) in enumerate(zip(self.names,self.cols)) if isGoal(s)}
    self.xs   = {n:c for n,(s,c) in enumerate(zip(self.names,self.cols)) 
                 if not isGoal(s) and s[-1] != "X"}
    [self.add(row) for row in rows] 
    if order: self.ordered()

  def ordered(self):
    self.rows = sorted(self.rows, key = self.d2h)

  def add(self,row): 
    self.rows += [row] 
    [col.add(x) for x,col in zip(row,self.cols) if x != "?"]

  def clone(self, rows=[], order=False):
    return DATA([self.names] + rows, order=order)

  def d2h(self,lst):
    nom = sum(abs(col.heaven - col.norm(lst[n]))**2 for n,col in self.ys.items())
    return (nom / len(self.ys))**.5

  def mid(self): 
    return [max(col,key=col.get) if isa(col,SYM) else col.mu for col in self.cols]

  def div(self):
    return [col.entropy() if isa(col,SYM) else col.sd for col in self.cols]
  
  def convertToItems(self):
    yNames = []
    xNames = []
    for i, col in enumerate(self.cols):
      if col not in self.ys.values():
        xNames.append(self.names[i])
      if col in self.ys.values():
        yNames.append(self.names[i])
    values, yMatrix, xMatrix = [], [], []
    for i, row in enumerate(self.rows):
      xs, ys = [], []
      for j, col in enumerate(row):
        if j not in self.ys:
          xs.append(row[j])
        if j in self.ys:
          ys.append(row[j])
        yMatrix.append(ys)
        xMatrix.append(xs)
    # normalize values
    yMatrix = np.array(yMatrix)
    yMatrix = (yMatrix - yMatrix.min(0)) / yMatrix.ptp(0)
    values = xMatrix
    xMatrix = np.array(xMatrix)
    xMatrix = (xMatrix - xMatrix.min(0)) / xMatrix.ptp(0)
    std_div = np.std(xMatrix, axis=0)
    normRows = [None] * len(self.rows)
    for i, row in enumerate(self.rows):
      normRows[i] = (i, values[i], xNames, yMatrix[i], yNames, xMatrix[i], xNames)
    return normRows, std_div
  
#                                  _     
#          _  |   _.   _   _  o  _|_     
#         (_  |  (_|  _>  _>  |   |   \/ 
#                                     /  

  def loglike(self,row,nall,nh,m=1,k=2):
    def num(col,x):
      v     = col.sd**2 + tiny
      nom   = math.e**(-1*(x - col.mu)**2/(2*v)) + tiny
      denom = (2*math.pi*v)**.5
      return min(1, nom/(denom + tiny))
    def sym(col,x):
      return (col.get(x, 0) + m*prior) / (len(self.rows) + m)
    #------------------------------------------
    prior = (len(self.rows) + k) / (nall + k*nh)
    out   = math.log(prior)
    for c,x in etc.slots(row):
      if x != "?" and c not in self.ys:
        col  = self.cols[c]
        out += math.log((sym if isa(col,SYM) else num)(col, x))
    return out
            
#          _   ._   _|_  o  ._ _   o  _    _   /| 
#         (_)  |_)   |_  |  | | |  |  /_  (/_   | 
#              |                                  

  def smo(self, score=lambda B,R: 2*B-R, fun=None):
    def like(row,data):
      return data.loglike(row,len(data.rows),2,the.m,the.m)
    def acquire(best, rest, rows):
      chop=int(len(rows) * the.upper)
      return sorted(rows, key=lambda r: -score(like(r,best),like(r,rest)))[:chop]
    #-----------
    random.shuffle(self.rows)
    done, todo = self.rows[:the.budget0], self.rows[the.budget0:]
    data1 = self.clone(done, order=True)
    for i in range(the.Budget):
      if len(todo) < 3: break
      n = int(len(done)**the.Top + .5)
      top,*todo = acquire(self.clone(data1.rows[:n]),
                          self.clone(data1.rows[n:]),
                          todo)
      done.append(top)
      data1 = self.clone(done, order=True)
    return data1.rows[0]
                                     
#          _  |        _  _|_   _   ._ 
#         (_  |  |_|  _>   |_  (/_  |  
                                      
  def dist(self,row1,row2):
    def sym(_,x,y): 
      return 1 if x=="?" and y=="?" else (0 if x==y else 1)     
    def num(col,x,y):
      if x=="?" and y=="?" : return 1 
      x, y = col.norm(x), col.norm(y) 
      if x=="?" : x= 1 if y<.5 else 0
      if y=="?" : y= 1 if x<.5 else 0 
      return abs(x-y)  
    #-----------------
    d, n, p = 0, 0, the.p
    for c,col in  enumerate(self.cols):
      if c not in self.ys:
        n   = n + 1
        inc = (sym if isa(col,SYM) else num)(col, row1[c],row2[c])
        d   = d + inc**p 
    return (d/n)**(1/p) 

  def near(self, row1, rows=None):
    return sorted(rows or self.rows, key=lambda row2: self.dist(row1,row2))

  def far(self, rows, sortp=False, before=None):
    n     = int(len(rows) * the.Far)
    left  = before or self.near(random.choice(rows),rows)[n]
    right = self.near(left,rows)[n]
    if sortp and self.d2h(right) < self.d2h(left): left,right = right,left
    return left, right 
    
  def half(self, rows, sortp=False, before=None):
    def dist(r1,r2): return self.dist(r1, r2)
    def proj(row)  : return (dist(row,left)**2 + C**2 - dist(row,right)**2)/(2*C)
    left,right = self.far(random.choices(rows, k=min(the.Half, len(rows))),
                          sortp=sortp, before=before)
    lefts,rights,C = [],[], dist(left,right)
    for n,row in enumerate(sorted(rows, key=proj)):  
      (lefts if n < len(rows)/2 else rights).append(row)
    return lefts, rights, left
  
#                                              _  
#          _   ._   _|_  o  ._ _   o  _    _    ) 
#         (_)  |_)   |_  |  | | |  |  /_  (/_  /_ 
#              |                                  

  def branch(self, rows=None, stop=None, rest=None, evals=1, before=None):
    rows = rows or self.rows
    stop = stop or 2*len(rows)**the.Min
    rest = rest or []
    if len(rows) > stop:
      lefts,rights,left  = self.half(rows, True, before)
      return self.branch(lefts, stop, rest+rights, evals+1, left)
    else:
      return rows,rest,evals,before
    
  def rtree(self, items=None, stop=None):
    stop = stop or 2*len(items)**the.Min
    if len(items) > stop:
      leftN, leftR, rightN, rightR = self.sneak_fastmap(items)
      leftN.left, leftN.lefts, leftN.leftR, leftN.right, leftN.rights, leftN.rightR = self.rtree(items = leftN.all, stop = stop)
      rightN.left, rightN.lefts, rightN.leftR, rightN.right, rightN.rights, rightN.rightR = self.rtree(items = rightN.all,stop =  stop)
      return leftN, leftN.all, leftR,  rightN, rightN.all, rightR
    return None, None, None, None, None, None
  
  def sneak_fastmap(self, items):
    rand = random.choice(items)
    max_d = float("-inf")
    left = None
    for item in items:
      d = self.sneak_dist(item, rand)
      if d > max_d:
        max_d = d
        left = item
    
    max_d = float("-inf")
    right = None
    for item in items:
      d = self.sneak_dist(item, left)
      if d > max_d:
        max_d = d
        right = item

    c = self.sneak_dist(left, right)

    for item in items:
      a = self.sneak_dist(item, left)
      b = self.sneak_dist(item, right)
      item.d = (a**2 + c**2 - b**2) / (2*c)
    
    items.sort(key = lambda x: x.d)
    
    n = len(items)

    lefts,rights = items[:int(n/2)], items[int(n/2):]

    return Node(None, None, None, None, None, None, lefts), left, Node(None, None, None, None, None, None, rights), right



  def sneak_dist(self, a, b):
    def num(p, q):
      return abs(p - q)
    def sym(p, q):
      return p != q
    
    names = a.xNames
    d, n, p = 0, 0, the.p

    for i, name in enumerate(names):
      n += 1
      inc = (num if name[0].isupper() else sym)(a.xValues[i], b.xValues[i])      
      d += inc ** p

    return (d/n) ** (1/p)
  
  def tree(self):
    normRows, self.std_div = self.convertToItems()
    items = [Item(row) for row in normRows]
    left, lefts, leftR, right, rights, rightR, = self.rtree(items = items)
    root = Node(left, leftR, right, rightR, lefts, rights, items)
    return root
  
  def SNEAK(self, variant = 0):
    #create a tree
    self._sneak_var = variant
    self._eval_count = 0
    root = self.tree()
    dfd = self.calculateDfd(root)
    best, bestS = self.findGood(root, dfd)
    while bestS != 0 and best != None:
      self.decide(best, root)
      best, bestS = self.findGood(root, dfd)
    survivors = self.gatherSurvivors(root)
    if self._sneak_var >> 0 & 1:
      self._eval_count += len(survivors)
      mapped_survivors = [None] * len(survivors)
      for i in range(len(survivors)):
        mapped_survivors[i] = self.rows[survivors[i].pos]      
      mapped_survivors = sorted(mapped_survivors, key = self.d2h)
      return mapped_survivors[0], self._eval_count
    else:
      #print("Sneak left ", len(survivors), "candidate survivors")
      # sort survivors using the better function
      #survivors.sort()
      #print(survivors[0])
      return self.rows[survivors[0].pos], self._eval_count
    
  def findGood(self, root, dfd):
    #for each node calculate the good score
    #return the node with the highest good score
    entropy = self.getEntropy(root)
    goodV = self.calculateGoodV(dfd, entropy)
    goodNode = root
    goodScore = self.goodScore(root, goodV)
    if root.left != None:
      goodNodeL, goodScoreL = self.findGoodR(root.left, goodV, goodScore)
      if goodScoreL > goodScore:
        goodNode = goodNodeL
        goodScore = goodScoreL
    if root.right != None:
      goodNodeR, goodScoreR = self.findGoodR(root.right, goodV, goodScore)
      if goodScoreR > goodScore:
        goodNode = goodNodeR
        goodScore = goodScoreR
    return goodNode, goodScore
    
    #walk the tree and calculate goodNode for each node keeping track of the best node

  def findGoodR(self, node, goodV, goodScore):
    goodNode = None
    goodScore = 0
    if node.left != None and node.right != None:
      goodScore = self.goodScore(node, goodV)
      goodNode = node
    if node.left != None:
      goodNodeL, goodScoreL = self.findGoodR(node.left, goodV, goodScore)
      if goodScoreL > goodScore:
        goodNode = goodNodeL
        goodScore = goodScoreL
    if node.right != None:
      goodNodeR, goodScoreR = self.findGoodR(node.right, goodV, goodScore)
      if goodScoreR > goodScore:
        goodNode = goodNodeR
        goodScore = goodScoreR
    return goodNode, goodScore

  def goodScore(self, node, goodV):
    def num(p, q):
      return abs(p - q)
    def sym(p, q):
      return p != q
    
    asked = 1 - node.asked
    good, denom = 0, 0
    for i, v in enumerate(goodV):
      diff = (num if node.leftR.xNames[i][0].isupper() else sym)(node.leftR.xValues[i], node.rightR.xValues[i])
      good += diff * v
      denom += diff
    good = good * asked 

    return 0 if denom == 0 else good/denom

  
  def calculateGoodV(self, dfd, entropy):
    goodV = []
    for i in range(len(dfd)):
      goodV.append(entropy[i]* (1 - dfd[i]))
    return goodV

  def calculateDfd(self, root):
    #walk the tree and calculate the depth of the first occurence of a difference in the left and right variables for each column in the data
    dfd = [0]*len(root.all[0].xValues)
    if root.left != None:
      dfdl = self.recursiveDfd(root.left, dfd, 1)
    if root.right != None:
      dfdr = self.recursiveDfd(root.right, dfd, 1)
    # merge dfdl and dfdr into dfd
    for i in range(len(dfd)):
      if dfdl[i] != 0 and dfdr[i] != 0:
        dfd[i] = min(dfdl[i], dfdr[i])
      elif dfdl[i] != 0:
        dfd[i] = dfdl[i]
      elif dfdr[i] != 0:
        dfd[i] = dfdr[i]
    #normalize dfd 0 to 1
    max_dfd = max(dfd)
    for i in range(len(dfd)):
      dfd[i] = dfd[i] / max_dfd
    return dfd
  
  def recursiveDfd(self, node, dfd, depth):

    def num(p, q, std):
      return abs(p - q) > std
    def sym(p, q, std):
      return p != q

    if node.right != None and node.left != None:
      for i in range(len(node.all[0].xValues)):
        diff = (num if node.leftR.xNames[i][0].isupper() else sym)(node.leftR.xValues[i], node.rightR.xValues[i], self.std_div[i])
        if diff and (dfd[i] == 0 or dfd[i] > depth):
          dfd[i] = depth
      if node.left != None:
        dfdl = self.recursiveDfd(node.left, dfd, depth + 1)
      if node.right != None:
        dfdr = self.recursiveDfd(node.right, dfd, depth + 1)
      # merge dfdl, dfdr and dfd into dfd
      for i in range(len(dfd)):
        if dfdl[i] != 0 and dfdr[i] != 0 and dfd[i] != 0:
          dfd[i] = min(dfdl[i], dfdr[i], dfd[i])
        elif dfdl[i] != 0 and dfdr[i] != 0:
          dfd[i] = min(dfdl[i], dfdr[i])
        elif dfdl[i] != 0 and dfd[i] != 0:
          dfd[i] = min(dfdl[i], dfd[i])
        elif dfdr[i] != 0 and dfd[i] != 0:
          dfd[i] = min(dfdr[i], dfd[i])
    return dfd
  
  def getEntropy(self, root):
    rows = [item.xValues for item in root.all]
    names = root.all[0].xNames
    data = DATA([names])
    for row in rows:
      data.add(row)
    entropy = data.div()
    return entropy
    
  def decide(self, node, root):
    self._eval_count += 2
    node.asked = 1
    # better returns 1 if left is better and 0 if right is better
    if self.better(node):
      self.prune(node.left, root)
      node.left = None
    else:
      self.prune(node.right, root)
      node.right = None
    return
  
  def better(self, node):
    # dynamic ziztler predicate comparing left and right representatives
    evNames = node.leftR.evNames
    left = node.leftR.ev
    right = node.rightR.ev
    s1, s2, n = 0, 0, len(evNames)
    for i, name in enumerate(evNames):
      a = left[i]
      b = right[i]
      multi = 1 if name[-1] == "+" else -1
      s1 -= math.e**(multi * (a-b)/n)
      s2 -= math.e**(multi * (b-a)/n)
    return s1 / n < s2 / n
  
  def prune(self, node, root):
    pruned = node.all
    for item in pruned:
      for ogItem in root.all:
        if item.item == ogItem.item:
          root.all.remove(ogItem)
          break
    #print("Pruned", len(pruned), "items now root has", len(root.all), "items")

  def gatherSurvivors(self, root):
    return root.all
  



class Node(struct):
  def __init__(self, left, leftR, right, rightR, lefts, rights, all):
    self.left = left
    self.leftR = leftR
    self.right = right
    self.rightR = rightR
    self.lefts = lefts
    self.rights = rights
    self.all = all
    self.asked = 0
  def __repr__(self):
    return f"Node(children={len(self.all)}\nleft={self.left}\nright={self.right})"


class Item(struct):
  def __init__(self, item):
    self.item = item[1]
    self.names = item[2]
    self.ev = item[3]
    self.evNames = item[4]
    self.xValues = item[5]
    self.xNames = item[6]
    self.r = -1
    self.d = -1
    self.theta = -1
    self.score = 0
    self.pos = item[0]
    self.features = sum(self.item)


  def better(self, other):
    # dynamic ziztler predicate comparing left and right representatives
    evNames = self.evNames
    left = self.ev
    right = other.ev
    s1, s2, n = 0, 0, len(evNames)
    for i, name in enumerate(evNames):
      a = left[i]
      b = right[i]
      multi = 1 if name[-1] == "+" else -1
      s1 -= math.e**(multi * (a-b)/n)
      s2 -= math.e**(multi * (b-a)/n)
    return s1 / n < s2 / n
  
  def __lt__(self, other):
    return self.better(other)

