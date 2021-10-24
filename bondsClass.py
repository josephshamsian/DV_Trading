# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import QuantLib as ql

class Bond:
    def __init__(self, issueDate, accrualDate, coupon, firstCouponDate, maturityDate, date, price):
        self.issueDate = pd.to_datetime(issueDate)
        self.accrualDate = pd.to_datetime(accrualDate)
        self.coupon = coupon/100.0
        self.firstCouponDate = pd.to_datetime(firstCouponDate)
        self.maturityDate = pd.to_datetime(maturityDate)
        self.date = pd.to_datetime(date)
        self.price = price
        self.face = 100.0
        
        start = ql.Date().from_date(self.accrualDate)
        maturity = ql.Date().from_date(self.maturityDate)
        self.schedule = ql.Schedule(start, maturity, ql.Period(ql.Semiannual), ql.UnitedStates(), ql.Unadjusted, ql.Unadjusted, ql.DateGeneration.Forward, True)
        
        self.maturity = None
        self.ytm = None
        self.duration = None
        self.accruedInterest = None
        self.DV01 = None
        
    def calculateMaturity(self):
        self.maturity = self.maturityDate.year - self.accrualDate.year
        return self.maturity
    
    def calculateYTM(self, settlementDate = ql.Date(12,10, 2021)):
        if self.ytm == None:
            start = ql.Date().from_date(self.accrualDate)
            interest = ql.FixedRateLeg(self.schedule, ql.ActualActual(), [self.face], [self.coupon])
            bond = ql.Bond(0, ql.UnitedStates(), start, interest)
            self.ytm = bond.bondYield(self.price, ql.ActualActual(), ql.Compounded, ql.Semiannual, settlementDate)
        return self.ytm
    
    def calculateDuration(self, settlementDays=0):
        bond = ql.FixedRateBond(settlementDays, self.face, self.schedule, [self.coupon], ql.ActualActual())
        rate = ql.InterestRate(self.calculateYTM(), ql.ActualActual(), ql.Compounded, ql.Semiannual)
        self.duration = ql.BondFunctions.duration(bond, rate, ql.Duration.Modified)
        return self.duration
        
    def calculateAccruedInterest(self, settlementDays=0):
        bond = ql.FixedRateBond(settlementDays, self.face, self.schedule, [self.coupon], ql.ActualActual())
        valuationDate = ql.Date().from_date(self.date)
        curve = ql.FlatForward(valuationDate, ql.QuoteHandle(ql.SimpleQuote(self.coupon)), ql.ActualActual(), ql.Compounded)
        
        handle = ql.YieldTermStructureHandle(curve)
        bondEngine = ql.DiscountingBondEngine(handle)
        bond.setPricingEngine(bondEngine)
        self.accruedInterest = bond.accruedAmount(valuationDate)
        return self.accruedInterest
    
    def calculateDV01(self, settlementDays=0):
        self.calculateYTM()
        bond = ql.FixedRateBond(settlementDays, self.face, self.schedule, [self.coupon], ql.ActualActual())
        rate = ql.InterestRate(self.ytm, ql.ActualActual(), ql.Compounded, ql.Semiannual)
        valuationDate = ql.Date().from_date(self.date)
        self.DV01 = ql.BondFunctions.basisPointValue(bond, rate,  valuationDate)
        return self.DV01


class Portfolio:
    def __init__(self):
        self.df = pd.read_csv("sample_portfolio.csv", index_col=0)
        self.df.rename(columns = {" PositionNotional ": "PositionNotional"}, inplace=True)
        self.df["PositionNotional"] = self.df["PositionNotional"].apply(lambda x: float(x.replace(",", "")))
        self.df["bondObj"] = self.df.apply(lambda x: Bond(x.IssueDate, x.AccrualDate, x.Coupon, x.FirstCouponDate, x.MaturityDate, x.Date, x.Price), axis=1)
        self.enrich()
        #self.getaggregateData()
        
    def enrich(self):
        self.df["maturity"] = self.df.apply(lambda x: x.bondObj.calculateMaturity(), axis=1)
        self.df["ytm"] = self.df.apply(lambda x: x.bondObj.calculateYTM(), axis=1)
        self.df["duration"] = self.df.apply(lambda x: x.bondObj.calculateDuration(), axis=1)
        self.df["accruedInterest"] = self.df.apply(lambda x: x.bondObj.calculateAccruedInterest(), axis=1)
        self.df["DV01"] = self.df.apply(lambda x: x.bondObj.calculateDV01(), axis=1)
        
    def computeNotional(self, maturity):
        return self.df[self.df["maturity"] == maturity]["PositionNotional"].sum()
        
    def computeDV01(self, maturity):
        dfcopy = self.df.copy()
        dfcopy["shares"] = dfcopy["PositionNotional"]/dfcopy["Price"]
        dfcopy["weightedDV01"] = dfcopy["shares"]*dfcopy["DV01"]
        return dfcopy[dfcopy["maturity"] == maturity]["weightedDV01"].sum()
        
    def computeAccruedInterest(self, maturity):
        return self.df[self.df["maturity"] == maturity]["accruedInterest"].sum()
        
    def getAggregateData(self):
        df_aggregate = pd.DataFrame()
        list_aggregate_notional = []
        list_aggregate_DV01 = []
        list_aggregate_AccruedInterest = []
        for maturity in self.df.maturity.unique():
            list_aggregate_notional.append(self.computeNotional(maturity))
            list_aggregate_DV01.append(self.computeDV01(maturity))
            list_aggregate_AccruedInterest.append(self.computeAccruedInterest(maturity))
        df_aggregate = pd.DataFrame({"Maturity": self.df.maturity.unique(), "Notional": list_aggregate_notional, 
         "DV01": list_aggregate_DV01, "AccruedInterest": list_aggregate_AccruedInterest})
        df_aggregate.set_index("Maturity", inplace = True)
        
        return df_aggregate
        
    def computePnL(self, yieldDeltas = [-25,-20,-15,-10,-5,5,10,15,20,25]):
        dict_PnL = {y : self.df.apply(lambda x: x.bondObj.DV01*x.PositionNotional*y/10000, axis=1).sum() for y in yieldDeltas}
        df_PnL = pd.DataFrame([dict_PnL]).T
        df_PnL.reset_index(level=0, inplace=True)
        df_PnL.columns = ["YieldMove", "PortfolioPnL"]
        df_PnL.set_index("YieldMove", inplace =True)
        return df_PnL
    
p = Portfolio()
print("1: Calculate the yield to matrity, duration, DV01 and accrued interest for each bond", '\n')
print(p.df[[ "ytm", "duration", "accruedInterest", "DV01"]], '\n')

print("2. Aggregated DV01/Accrued interest/Notional on the maturity buckets: 5Y/10Y/20Y/30Y", '\n')
print(p.getAggregateData(), '\n')

print("3. Assume the bond yield is up/down  5,10,15,20,25  basis points, calculate the portfolio PnL")
df_PnL = p.computePnL()
print(df_PnL)