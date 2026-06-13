import os
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox

# ==========================================
# CUSTOM EXCEPTIONS (Robust Error Handling)
# ==========================================
class BloodBankException(Exception):
    """Base exception for the Blood Bank System"""
    pass

class IneligibleDonorException(BloodBankException):
    """Raised when a donor fails medical or timeline eligibility criteria"""
    pass

class BloodStockShortageException(BloodBankException):
    """Raised when requested blood units exceed available inventory"""
    pass

# ==========================================
# CORE ABSTRACTION & OOP MODELS
# ==========================================
class Person(ABC):
    """Abstract Base Class demonstrating Abstraction and Inheritance"""
    def __init__(self, person_id, name, age, gender, phone):
        self.id = person_id
        self.name = name
        self.age = age
        self.gender = gender
        self.phone = phone

    @abstractmethod
    def display_details(self):
        pass

class Donor(Person):
    """Derived Class demonstrating Encapsulation and Polymorphism"""
    def __init__(self, donor_id, name, age, gender, phone, blood_group, weight, hemoglobin, last_donation_str=""):
        super().__init__(donor_id, name, age, gender, phone)
        self.blood_group = blood_group
        # Encapsulating medical attributes with double underscores
        self.__weight = float(weight)
        self.__hemoglobin = float(hemoglobin)
        self.__last_donation = last_donation_str

    # Getters and Setters for encapsulated fields
    @property
    def weight(self): return self.__weight
    
    @property
    def hemoglobin(self): return self.__hemoglobin
    
    @property
    def last_donation(self): return self.__last_donation

    def check_eligibility(self):
        """Validates standard medical parameters and 90-day deferral windows"""
        if self.age < 18 or self.age > 65:
            return False, "Age must be between 18 and 65 years."
        if self.__weight < 50.0:
            return False, "Weight must be at least 50 kg."
        if self.__hemoglobin < 12.5:
            return False, "Hemoglobin level must be at least 12.5 g/dL."
        
        if self.__last_donation:
            try:
                last_date = datetime.strptime(self.__last_donation, "%Y-%m-%d")
                days_since = (datetime.now() - last_date).days
                if days_since < 90:
                    return False, f"Deferred. Only {days_since} days since last donation (90 days required)."
            except ValueError:
                return False, "Invalid date format in records."
        
        return True, "Eligible to donate."

    def display_details(self):
        return f"Donor [{self.id}] {self.name} | Group: {self.blood_group}"

    def to_dict(self):
        """Helper for JSON Serialization"""
        return {
            "id": self.id, "name": self.name, "age": self.age, "gender": self.gender,
            "phone": self.phone, "blood_group": self.blood_group, "weight": self.__weight,
            "hemoglobin": self.__hemoglobin, "last_donation": self.__last_donation
        }

class BloodBag:
    """Represents an inventory item with automatic expiration parsing"""
    def __init__(self, bag_id, blood_group, volume_ml, donation_date_str=None):
        self.bag_id = bag_id
        self.blood_group = blood_group
        self.volume_ml = int(volume_ml)
        
        if donation_date_str:
            self.donation_date = datetime.strptime(donation_date_str, "%Y-%m-%d")
        else:
            self.donation_date = datetime.now()
            
        # Shelf life logic: Whole blood expires in 42 days
        self.expiry_date = self.donation_date + timedelta(days=42)

    def is_expired(self):
        return datetime.now() > self.expiry_date

    def to_dict(self):
        return {
            "bag_id": self.bag_id,
            "blood_group": self.blood_group,
            "volume_ml": self.volume_ml,
            "donation_date": self.donation_date.strftime("%Y-%m-%d")
        }

# ==========================================
# SYSTEM CONTROLLER (Composition Pattern)
# ==========================================
class BloodBankSystem:
    """Manages business logic, memory states, and JSON file I/O"""
    def __init__(self):
        self.donors = {}         # Dictionary (Key: donor_id, Value: Donor Object)
        self.inventory = []      # List of BloodBag Objects
        self.db_dir = "database"
        
        if not os.path.exists(self.db_dir):
            os.makedirs(self.db_dir)
        self.load_data()

    def add_donor(self, donor: Donor):
        eligible, reason = donor.check_eligibility()
        if not eligible:
            raise IneligibleDonorException(reason)
        self.donors[donor.id] = donor
        self.save_data()

    def add_blood_bag(self, bag: BloodBag):
        self.inventory.append(bag)
        self.save_data()

    def issue_blood(self, blood_group, quantity):
        """Fulfills units using FIFO sorting; discards expired stock on the fly"""
        # Lambda function to sort stock by expiration date
        self.inventory.sort(key=lambda x: x.expiry_date)
        
        # Generator pattern to filter out valid, unexpired stock
        valid_stock = (bag for bag in self.inventory if not bag.is_expired() and bag.blood_group == blood_group)
        
        matching_bags = []
        allocated_volume = 0
        target_volume = int(quantity) * 350 # Estimating 350ml standard per unit bag
        
        for bag in valid_stock:
            if allocated_volume >= target_volume:
                break
            matching_bags.append(bag)
            allocated_volume += bag.volume_ml

        if allocated_volume < target_volume:
            raise BloodStockShortageException(f"Insufficient stock for {blood_group}. Needed approx {target_volume}ml, found only {allocated_volume}ml.")

        # Remove issued bags from active tracking
        for bag in matching_bags:
            self.inventory.remove(bag)
        
        self.save_data()
        return len(matching_bags), allocated_volume

    def get_stock_summary(self):
        """Calculates exact unit metrics dynamically using list comprehensions"""
        groups = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
        summary = {g: 0 for g in groups}
        for bag in self.inventory:
            if not bag.is_expired() and bag.blood_group in summary:
                summary[bag.blood_group] += 1
        return summary

    def save_data(self):
        """Serializes current runtime collections to local JSON storage files"""
        with open(os.path.join(self.db_dir, "donors.json"), "w") as f:
            json.dump({k: v.to_dict() for k, v in self.donors.items()}, f, indent=4)
        with open(os.path.join(self.db_dir, "inventory.json"), "w") as f:
            json.dump([bag.to_dict() for bag in self.inventory], f, indent=4)

    def load_data(self):
        """De-serializes stored persistent entities back into live active objects"""
        try:
            donors_path = os.path.join(self.db_dir, "donors.json")
            if os.path.exists(donors_path):
                with open(donors_path, "r") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.donors[k] = Donor(v['id'], v['name'], v['age'], v['gender'], v['phone'], v['blood_group'], v['weight'], v['hemoglobin'], v['last_donation'])
            
            inv_path = os.path.join(self.db_dir, "inventory.json")
            if os.path.exists(inv_path):
                with open(inv_path, "r") as f:
                    data = json.load(f)
                    self.inventory = [BloodBag(b['bag_id'], b['blood_group'], b['volume_ml'], b['donation_date']) for b in data]
        except Exception as e:
            print(f"Error loading system configuration states: {e}")

# ==========================================
# MODERN GUI APPLICATION WORKFRAME (Tkinter)
# ==========================================
class BloodBankGUI(tk.Tk):
    def __init__(self, system_controller):
        super().__init__()
        self.system = system_controller
        self.title("LifeFlow | Blood Bank Management System")
        self.geometry("1000x620")
        self.configure(bg="#2d2d2d") # Charcoal Black Dark Theme Background
        
        self.setup_styles()
        self.build_layout()
        self.refresh_dashboard()

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Theme configuration mappings
        self.style.configure("TFrame", background="#2d2d2d")
        self.style.configure("Card.TFrame", background="#3d3d3d", relief="raised", borderwidth=1)
        self.style.configure("TLabel", background="#2d2d2d", foreground="#ffffff", font=("Helvetica", 10))
        self.style.configure("Title.TLabel", font=("Helvetica", 16, "bold"), foreground="#ff4d4d", background="#2d2d2d")
        self.style.configure("CardTitle.TLabel", font=("Helvetica", 11, "bold"), background="#3d3d3d", foreground="#aaaaaa")
        self.style.configure("CardVal.TLabel", font=("Helvetica", 20, "bold"), background="#3d3d3d", foreground="#ff4d4d")
        
        self.style.configure("TButton", font=("Helvetica", 10, "bold"), foreground="#ffffff", background="#4a4a4a", borderwidth=0, padding=6)
        self.style.map("TButton", background=[("active", "#ff4d4d"), ("hover", "#ff4d4d")])
        self.style.configure("Action.TButton", background="#ff4d4d")

    def build_layout(self):
        # Header Canvas Container Area
        header = ttk.Frame(self, padding=10)
        header.pack(fill="x", side="top")
        ttk.Label(header, text="🩸 LifeFlow Management Dashboard", style="Title.TLabel").pack(side="left", padx=10)
        
        # Main Window Work Split Panels
        main_container = ttk.Frame(self, padding=10)
        main_container.pack(fill="both", expand=True)
        
        left_panel = ttk.Frame(main_container, width=300)
        left_panel.pack(side="left", fill="y", padx=5)
        
        right_panel = ttk.Frame(main_container)
        right_panel.pack(side="right", fill="both", expand=True, padx=5)

        # ----------------- Left Panel: Action Buttons -----------------
        btn_config = [
            ("Register New Donor", self.open_donor_window),
            ("Log New Donation", self.open_donation_window),
            ("Issue Blood Stock", self.open_issue_window),
            ("View Registered Donors", self.view_donors_window)
        ]
        
        for text, command in btn_config:
            btn = ttk.Button(left_panel, text=text, command=command, width=25)
            btn.pack(fill="x", pady=8, ipady=4)

        # ----------------- Right Panel: Stock Metrics Overview -----------------
        lbl_sec = ttk.Label(right_panel, text="Real-Time Available Blood Stock Units (Whole Blood Bags)", font=("Helvetica", 12, "bold"))
        lbl_sec.pack(anchor="w", pady=(0, 10))
        
        self.cards_frame = ttk.Frame(right_panel)
        self.cards_frame.pack(fill="both", expand=True)

    def refresh_dashboard(self):
        """Clears and rebuilds grid element card summaries to present fresh telemetry data"""
        for widget in self.cards_frame.winfo_children():
            widget.destroy()

        stock_data = self.system.get_stock_summary()
        
        # Programmatically plot dynamic grid components
        columns = 4
        for idx, (group, count) in enumerate(stock_data.items()):
            r = idx // columns
            c = idx % columns
            
            card = ttk.Frame(self.cards_frame, style="Card.TFrame", padding=15)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")
            
            ttk.Label(card, text=f"Type {group}", style="CardTitle.TLabel").pack(anchor="center")
            ttk.Label(card, text=str(count), style="CardVal.TLabel").pack(anchor="center", pady=(5, 0))
            
            self.cards_frame.grid_columnconfigure(c, weight=1)

    # ----------------- SUB-WINDOW FORMS & INTERFACE MODALS -----------------
    def open_donor_window(self):
        win = tk.Toplevel(self)
        win.title("Donor Registration System")
        win.geometry("400x450")
        win.configure(bg="#2d2d2d")

        fields = [
            ("Donor ID (Unique):", "id"), ("Full Name:", "name"), ("Age:", "age"),
            ("Gender:", "gender"), ("Phone Target:", "phone"), ("Blood Group (e.g. O+):", "bg"),
            ("Weight (kg):", "weight"), ("Hemoglobin (g/dL):", "hb"), ("Last Donation (YYYY-MM-DD or leave blank):", "ld")
        ]
        entries = {}

        for lbl_text, key in fields:
            f = ttk.Frame(win, padding=5)
            f.pack(fill="x")
            ttk.Label(f, text=lbl_text, width=35, anchor="w").pack(side="left", padx=5)
            ent = ttk.Entry(f)
            ent.pack(side="right", expand=True, fill="x", padx=5)
            entries[key] = ent

        def submit():
            try:
                # Validation checks
                if not entries['id'].get() or not entries['name'].get():
                    raise ValueError("ID and Name fields cannot be empty.")
                
                new_donor = Donor(
                    entries['id'].get(), entries['name'].get(), int(entries['age'].get()),
                    entries['gender'].get(), entries['phone'].get(), entries['bg'].get().upper(),
                    entries['weight'].get(), entries['hb'].get(), entries['ld'].get()
                )
                self.system.add_donor(new_donor)
                messagebox.showinfo("Success", f"Donor {new_donor.name} registered and saved successfully!", parent=win)
                win.destroy()
            except IneligibleDonorException as ex:
                messagebox.showerror("Medical Rejection", f"Donor Ineligible: {ex}", parent=win)
            except Exception as ex:
                messagebox.showerror("Data Formatting Error", f"Failed to parse configuration parameters: {ex}", parent=win)

        ttk.Button(win, text="Save Registration Profile", style="Action.TButton", command=submit).pack(pady=20)

    def open_donation_window(self):
        win = tk.Toplevel(self)
        win.title("Log Blood Unit Collection")
        win.geometry("400x250")
        win.configure(bg="#2d2d2d")

        fields = [("Associated Donor ID:", "id"), ("Unique Bag Serial Number:", "bag"), ("Volume Drawn (mL):", "vol")]
        entries = {}

        for lbl_text, key in fields:
            f = ttk.Frame(win, padding=8)
            f.pack(fill="x")
            ttk.Label(f, text=lbl_text, width=25, anchor="w").pack(side="left", padx=5)
            ent = ttk.Entry(f)
            ent.pack(side="right", expand=True, fill="x", padx=5)
            entries[key] = ent
        
        # Populate defaults
        entries['vol'].insert(0, "350")

        def submit():
            d_id = entries['id'].get()
            if d_id not in self.system.donors:
                messagebox.showerror("Error", "No registered donor profile maps to this ID index.", parent=win)
                return
            
            donor_obj = self.system.donors[d_id]
            eligible, reason = donor_obj.check_eligibility()
            if not eligible:
                messagebox.showerror("Medical Rejection", f"Donation aborted: {reason}", parent=win)
                return

            bag = BloodBag(entries['bag'].get(), donor_obj.blood_group, entries['vol'].get())
            self.system.add_blood_bag(bag)
            
            # Update donor's last donation date to today
            donor_obj._Donor__last_donation = datetime.now().strftime("%Y-%m-%d")
            self.system.save_data()
            
            messagebox.showinfo("Success", f"Blood Bag {bag.bag_id} added to stock inventory.", parent=win)
            self.refresh_dashboard()
            win.destroy()

        ttk.Button(win, text="Log Unit Bag Verification", style="Action.TButton", command=submit).pack(pady=15)

    def open_issue_window(self):
        win = tk.Toplevel(self)
        win.title("Requisition Distribution Order Form")
        win.geometry("400x220")
        win.configure(bg="#2d2d2d")

        fields = [("Requested Blood Type:", "bg"), ("Number of Bags (Units Needed):", "units")]
        entries = {}

        for lbl_text, key in fields:
            f = ttk.Frame(win, padding=10)
            f.pack(fill="x")
            ttk.Label(f, text=lbl_text, width=25, anchor="w").pack(side="left", padx=5)
            ent = ttk.Entry(f)
            ent.pack(side="right", expand=True, fill="x", padx=5)
            entries[key] = ent

        def submit():
            bg_req = entries['bg'].get().upper()
            qty = entries['units'].get()
            try:
                bags_count, vol = self.system.issue_blood(bg_req, qty)
                messagebox.showinfo("Order Allocation Successful", f"Dispatched {bags_count} bags totaling {vol}mL of Type {bg_req}.", parent=win)
                self.refresh_dashboard()
                win.destroy()
            except BloodStockShortageException as ex:
                messagebox.showerror("Inventory Shortage Exception", str(ex), parent=win)
            except Exception as ex:
                messagebox.showerror("Error", f"Could not process checkout order criteria: {ex}", parent=win)

        ttk.Button(win, text="Approve Distribution Line", style="Action.TButton", command=submit).pack(pady=15)

    def view_donors_window(self):
        win = tk.Toplevel(self)
        win.title("Active Database Registry Profiles")
        win.geometry("600x400")
        win.configure(bg="#2d2d2d")

        txt = tk.Text(win, bg="#1e1e1e", fg="#ffffff", insertbackground="white", wrap="word", font=("Courier", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        if not self.system.donors:
            txt.insert("1.0", "No donor entries are currently registered in the system.")
        else:
            for idx, donor in enumerate(self.system.donors.values(), start=1):
                txt.insert("end", f"{idx}. {donor.display_details()} | Phone: {donor.phone} | Age: {donor.age}\n")
        txt.config(state="disabled")

# ==========================================
# ENTRYPOINT RUN METHOD
# ==========================================
if __name__ == "__main__":
    # Instantiate the controller engine state matrix
    backend_system = BloodBankSystem()
    
    # Bootstrap the Tkinter application framework view
    app = BloodBankGUI(backend_system)
    app.mainloop()