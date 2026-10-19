def calculate_trend(values,metric=None):
 ordered=sorted(values,key=lambda x:x[0] if isinstance(x,(tuple,list)) else x["measured_at"])
 if len(ordered)<2:return {"status":"insufficient_data","direction":"insufficient_data","change":None,"percentage_change":None}
 def unpack(x):return (x[1],x[2]) if isinstance(x,(tuple,list)) else (x["value"],x["unit"])
 first,last=unpack(ordered[0]),unpack(ordered[-1])
 if first[1]!=last[1]:return {"status":"incomparable_units","direction":"incomparable","change":None,"percentage_change":None}
 change=last[0]-first[0]; pct=None if first[0]==0 else change/first[0]*100
 direction="stable" if change==0 else "up" if change>0 else "down"
 return {"status":"ok","direction":direction,"change":round(change,4),"percentage_change":None if pct is None else round(pct,4),"unit":first[1],"percentage_point_change":round(change,4) if first[1]=="%" else None}
