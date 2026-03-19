"""
Interactive Wind Map Application with Drag & Drop
Displays mean wind speed maps and time series from NetCDF files
"""

import tkinter as tk
from tkinter import ttk, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from datetime import datetime


class WindMapApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interactive Wind Map Viewer")
        self.root.geometry("1600x800")
        
        # Data storage
        self.ds = None
        self.wind_data = None
        self.wind_var = None
        self.x_name = None
        self.y_name = None
        self.wind_mean = None
        self.selected_point = None
        self.selection_patch = None  # Store the selection rectangle
        self.hover_patch = None  # Store the hover rectangle
        self.hover_annotation = None  # Store hover text annotation
        self.colorbar = None  # Store the colorbar reference
        self.mean_min = None  # Store mean data min for consistent colorbar
        self.mean_max = None  # Store mean data max for consistent colorbar
        self.timestep_min = None  # Store timestep data min for consistent colorbar
        self.timestep_max = None  # Store timestep data max for consistent colorbar
        
        # View mode controls
        self.view_mode = tk.StringVar(value="Mean")
        self.current_timestep = tk.IntVar(value=1)
        self.max_timestep = 0
        
        # Animation controls
        self.is_animating = False
        self.animation_timer = None

        # Timestep range for time series display
        self.ts_first_timestep = tk.IntVar(value=1)
        self.ts_last_timestep = tk.IntVar(value=0)  # Will be set after loading data
        
        # Create GUI
        self.setup_gui()
        
    def setup_gui(self):
        """Setup the main GUI layout"""
        # Top frame for file path display
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        ttk.Label(top_frame, text="NetCDF File:").grid(row=0, column=0, sticky=tk.W)
        self.file_label = ttk.Label(top_frame, text="Drag and drop a NetCDF file here", 
                                     foreground="gray", font=("Arial", 10, "italic"))
        self.file_label.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=10)
        top_frame.columnconfigure(1, weight=1)
        
        # Control frame for view mode and timestep selection
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        # View mode dropdown
        ttk.Label(control_frame, text="View Mode:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.mode_combo = ttk.Combobox(control_frame, textvariable=self.view_mode, 
                                       values=["Mean", "Single Timestep"], 
                                       state="readonly", width=15)
        self.mode_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        self.mode_combo.bind('<<ComboboxSelected>>', self.on_mode_change)
        
        # Timestep controls (initially hidden)
        self.timestep_frame = ttk.Frame(control_frame)
        self.timestep_frame.grid(row=0, column=2, sticky=tk.W)
        
        ttk.Label(self.timestep_frame, text="Timestep:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.minus_btn = ttk.Button(self.timestep_frame, text="-", width=3, 
                                    command=self.decrease_timestep)
        self.minus_btn.pack(side=tk.LEFT, padx=2)
        
        self.timestep_entry = ttk.Entry(self.timestep_frame, textvariable=self.current_timestep, 
                                        width=8, justify=tk.CENTER)
        self.timestep_entry.pack(side=tk.LEFT, padx=2)
        self.timestep_entry.bind('<Return>', self.on_timestep_entry)
        
        self.plus_btn = ttk.Button(self.timestep_frame, text="+", width=3, 
                                   command=self.increase_timestep)
        self.plus_btn.pack(side=tk.LEFT, padx=2)
        
        self.timestep_info = ttk.Label(self.timestep_frame, text="/ --")
        self.timestep_info.pack(side=tk.LEFT, padx=(5, 0))
        
        # Animation button
        self.animate_btn = ttk.Button(self.timestep_frame, text="Start Animation", 
                                      command=self.toggle_animation)
        self.animate_btn.pack(side=tk.LEFT, padx=(20, 0))
        
        # Initially hide timestep controls
        self.timestep_frame.grid_remove()
        
        # Main container frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # Left panel - Map
        self.map_frame = ttk.LabelFrame(main_frame, text="Map", padding="5")
        self.map_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        
        # Coordinates display below map
        self.coord_frame = ttk.Frame(self.map_frame)
        self.coord_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))

        self.coord_label = ttk.Label(self.coord_frame, text="Selected: --", 
                         font=('Courier', 9))
        self.coord_label.pack(side=tk.LEFT)

        # Timestep range controls for time series (now created after ts_frame exists)
        # Moved to setup_ts_plot
        
        # Right panel - Time series
        self.ts_frame = ttk.LabelFrame(main_frame, text="Time Series", padding="5")
        self.ts_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        
        # Configure root grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        
        # Setup matplotlib figures
        self.setup_map_plot()
        self.setup_ts_plot()
        
        # Enable drag and drop
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.on_drop)
        
    def setup_map_plot(self):
        """Setup the map matplotlib figure"""
        self.map_fig = Figure(figsize=(8, 5.5), dpi=100)
        self.map_ax = self.map_fig.add_subplot(111, projection=ccrs.PlateCarree())
        
        # Initial empty plot
        self.map_ax.text(0.5, 0.5, 'Drop a NetCDF file to begin', 
                        transform=self.map_ax.transAxes,
                        ha='center', va='center', fontsize=14, color='gray')
        self.map_ax.set_global()
        
        self.map_canvas = FigureCanvasTkAgg(self.map_fig, master=self.map_frame)
        self.map_canvas.draw()
        self.map_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Add navigation toolbar for zoom/pan
        self.map_toolbar = NavigationToolbar2Tk(self.map_canvas, self.map_frame, pack_toolbar=False)
        self.map_toolbar.update()
        self.map_toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind events
        self.map_canvas.mpl_connect('button_press_event', self.on_map_click)
        self.map_canvas.mpl_connect('motion_notify_event', self.on_map_hover)
        self.map_canvas.mpl_connect('scroll_event', self.on_map_scroll)
        
    def setup_ts_plot(self):
        """Setup the time series matplotlib figure and timestep range controls"""
        self.ts_fig = Figure(figsize=(8, 6), dpi=100)
        self.ts_ax = self.ts_fig.add_subplot(111)

        # Timestep range controls for time series (now at top of time series panel)
        self.ts_range_frame = ttk.Frame(self.ts_frame)
        self.ts_range_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 2))
        ttk.Label(self.ts_range_frame, text="Show timesteps from").pack(side=tk.LEFT, padx=(0,2))
        self.ts_first_entry = ttk.Entry(self.ts_range_frame, textvariable=self.ts_first_timestep, width=6, justify=tk.CENTER)
        self.ts_first_entry.pack(side=tk.LEFT)
        ttk.Label(self.ts_range_frame, text="to").pack(side=tk.LEFT, padx=(2,2))
        self.ts_last_entry = ttk.Entry(self.ts_range_frame, textvariable=self.ts_last_timestep, width=6, justify=tk.CENTER)
        self.ts_last_entry.pack(side=tk.LEFT)
        self.ts_first_entry.bind('<Return>', lambda e: self.plot_time_series_selected())
        self.ts_last_entry.bind('<Return>', lambda e: self.plot_time_series_selected())

        # Initial empty plot
        self.ts_ax.text(0.5, 0.5, 'Click on the map to see time series', 
                       ha='center', va='center', fontsize=12, color='gray')
        self.ts_ax.set_xlim(0, 1)
        self.ts_ax.set_ylim(0, 1)
        self.ts_ax.axis('off')

        self.ts_canvas = FigureCanvasTkAgg(self.ts_fig, master=self.ts_frame)
        self.ts_canvas.draw()
        self.ts_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
    def on_drop(self, event):
        """Handle drag and drop event"""
        # Get file path (remove curly braces if present)
        file_path = event.data.strip('{}')
        
        # Load the NetCDF file
        try:
            self.load_netcdf(file_path)
            self.file_label.config(text=file_path, foreground="black", 
                                  font=("Arial", 10, "normal"))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load NetCDF file:\n{str(e)}")
            
    def load_netcdf(self, file_path):
        """Load and process NetCDF file"""
        # Stop animation if running
        if self.is_animating:
            self.stop_animation()
        
        # Close old dataset if it exists
        if self.ds is not None:
            try:
                self.ds.close()
            except:
                pass
        
        # Reset selection states
        self.selected_point = None
        if self.selection_patch is not None:
            try:
                self.selection_patch.remove()
            except:
                pass
            self.selection_patch = None
        if self.hover_patch is not None:
            try:
                self.hover_patch.remove()
            except:
                pass
            self.hover_patch = None
        if self.hover_annotation is not None:
            try:
                self.hover_annotation.remove()
            except:
                pass
            self.hover_annotation = None
        
        # Reset coordinate display
        self.coord_label.config(text="Selected: --")
        
        # Clear time series plot
        self.ts_ax.clear()
        self.ts_ax.text(0.5, 0.5, 'Click on the map to see time series', 
                       ha='center', va='center', fontsize=12, color='gray')
        self.ts_ax.set_xlim(0, 1)
        self.ts_ax.set_ylim(0, 1)
        self.ts_ax.axis('off')
        self.ts_canvas.draw()
        
        # Open dataset
        self.ds = xr.open_dataset(file_path)
        
        # Find wind variable (prefer wnd100m)
        if "wnd100m" in self.ds.data_vars:
            self.wind_var = "wnd100m"
        elif "wind" in self.ds.data_vars:
            self.wind_var = "wind"
        elif "wnd" in self.ds.data_vars:
            self.wind_var = "wnd"
        else:
            # Take first variable
            self.wind_var = list(self.ds.data_vars)[0]
            
        self.wind_data = self.ds[self.wind_var]
        
        # Determine coordinate names
        coords = list(self.wind_data.coords)
        
        # X coordinate
        if "x" in coords:
            self.x_name = "x"
        elif "lon" in coords:
            self.x_name = "lon"
        elif "longitude" in coords:
            self.x_name = "longitude"
        else:
            # Try to find any coordinate that looks like longitude
            for coord in coords:
                if coord.lower() in ['lon', 'long', 'longitude']:
                    self.x_name = coord
                    break
            if self.x_name is None:
                raise ValueError("Could not find longitude coordinate")
                
        # Y coordinate
        if "y" in coords:
            self.y_name = "y"
        elif "lat" in coords:
            self.y_name = "lat"
        elif "latitude" in coords:
            self.y_name = "latitude"
        else:
            # Try to find any coordinate that looks like latitude
            for coord in coords:
                if coord.lower() in ['lat', 'latitude']:
                    self.y_name = coord
                    break
            if self.y_name is None:
                raise ValueError("Could not find latitude coordinate")
        
        # Calculate mean wind speed
        self.wind_mean = self.wind_data.mean(dim="time")
        
        # Calculate data ranges for consistent colorbars
        # Range for mean view (based on mean data)
        self.mean_min = float(self.wind_mean.min().values)
        self.mean_max = float(self.wind_mean.max().values)
        
        # Range for single timestep view (based on all timesteps)
        self.timestep_min = float(self.wind_data.min().values)
        self.timestep_max = float(self.wind_data.max().values)
        
        # Initialize timestep controls
        self.max_timestep = len(self.wind_data['time'])
        self.current_timestep.set(1)
        self.timestep_info.config(text=f"/ {self.max_timestep}")

        # Set default time series range
        self.ts_first_timestep.set(1)
        self.ts_last_timestep.set(self.max_timestep)

        # Plot the map
        self.plot_map()
        
    def on_mode_change(self, event=None):
        """Handle view mode change"""
        # Stop animation when switching modes
        if self.is_animating:
            self.stop_animation()
        
        if self.view_mode.get() == "Single Timestep":
            self.timestep_frame.grid()
        else:
            self.timestep_frame.grid_remove()
        
        if self.wind_data is not None:
            self.plot_map()
    
    def increase_timestep(self):
        """Increase timestep by 1"""
        # Stop animation on manual change
        if self.is_animating:
            self.stop_animation()
        
        current = self.current_timestep.get()
        if current < self.max_timestep:
            self.current_timestep.set(current + 1)
            self.plot_map()
    
    def decrease_timestep(self):
        """Decrease timestep by 1"""
        # Stop animation on manual change
        if self.is_animating:
            self.stop_animation()
        
        current = self.current_timestep.get()
        if current > 1:
            self.current_timestep.set(current - 1)
            self.plot_map()
    
    def on_timestep_entry(self, event=None):
        """Handle manual timestep entry"""
        # Stop animation on manual change
        if self.is_animating:
            self.stop_animation()
        
        try:
            value = self.current_timestep.get()
            if value < 1:
                self.current_timestep.set(1)
            elif value > self.max_timestep:
                self.current_timestep.set(self.max_timestep)
            self.plot_map()
        except:
            self.current_timestep.set(1)
    
    def toggle_animation(self):
        """Toggle animation on/off"""
        if self.is_animating:
            self.stop_animation()
        else:
            self.start_animation()
    
    def start_animation(self):
        """Start the animation"""
        if self.wind_data is None:
            return
        
        self.is_animating = True
        self.animate_btn.config(text="Stop Animation")
        self.animate_step()
    
    def stop_animation(self):
        """Stop the animation"""
        self.is_animating = False
        self.animate_btn.config(text="Start Animation")
        
        # Cancel scheduled animation if exists
        if self.animation_timer is not None:
            self.root.after_cancel(self.animation_timer)
            self.animation_timer = None
    
    def animate_step(self):
        """Execute one step of animation"""
        if not self.is_animating:
            return
        
        current = self.current_timestep.get()
        
        # Check if we've reached the end
        if current >= self.max_timestep:
            self.stop_animation()
            return
        
        # Increment timestep and update map
        self.current_timestep.set(current + 1)
        self.plot_map()
        
        # Schedule next step (20ms = 0.02 seconds)
        self.animation_timer = self.root.after(20, self.animate_step)
    
    def plot_map(self):
        """Plot the wind speed map (mean or single timestep)"""
        # Remove old colorbar if it exists (before clearing axis)
        if self.colorbar is not None:
            try:
                self.colorbar.remove()
            except:
                pass
            self.colorbar = None
        
        # Clear the entire figure to remove all axes including colorbar axes
        self.map_fig.clear()
        
        # Reset patches since they're bound to the old axis
        self.selection_patch = None
        self.hover_patch = None
        self.hover_annotation = None
        
        # Recreate the map axis
        self.map_ax = self.map_fig.add_subplot(111, projection=ccrs.PlateCarree())
        
        # Get data and colorbar range based on view mode
        if self.view_mode.get() == "Mean":
            data_to_plot = self.wind_mean
            title_suffix = "Mean Wind Speed"
            vmin, vmax = self.mean_min, self.mean_max
        else:
            # Single timestep mode
            timestep_idx = self.current_timestep.get() - 1  # Convert to 0-based index
            data_to_plot = self.wind_data.isel(time=timestep_idx)
            time_value = data_to_plot['time'].values
            title_suffix = f"Wind Speed - Timestep {self.current_timestep.get()}"
            vmin, vmax = self.timestep_min, self.timestep_max
        
        # Get coordinates
        lons = data_to_plot[self.x_name].values
        lats = data_to_plot[self.y_name].values
        data = data_to_plot.values
        
        # Determine map extent
        lon_min, lon_max = float(lons.min()), float(lons.max())
        lat_min, lat_max = float(lats.min()), float(lats.max())
        
        # Add some padding
        lon_pad = (lon_max - lon_min) * 0.1
        lat_pad = (lat_max - lat_min) * 0.1
        
        self.map_ax.set_extent([lon_min - lon_pad, lon_max + lon_pad, 
                                lat_min - lat_pad, lat_max + lat_pad], 
                               crs=ccrs.PlateCarree())
        
        # Plot the data with consistent colorbar range
        mesh = self.map_ax.pcolormesh(lons, lats, data, 
                                      transform=ccrs.PlateCarree(),
                                      cmap='viridis', shading='auto',
                                      vmin=vmin, vmax=vmax)
        
        # Add colorbar
        self.colorbar = self.map_fig.colorbar(mesh, ax=self.map_ax, orientation='horizontal', 
                                      pad=0.05, shrink=0.8)
        self.colorbar.set_label(f'{self.wind_var} (m/s)', fontsize=10)
        
        # Add map features
        self.map_ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        self.map_ax.add_feature(cfeature.BORDERS, linewidth=0.3, linestyle=':')
        self.map_ax.add_feature(cfeature.LAND, alpha=0.1)
        
        # Add gridlines
        gl = self.map_ax.gridlines(draw_labels=True, linestyle='--', alpha=0.5)
        gl.top_labels = False
        gl.right_labels = False
        
        self.map_ax.set_title(f'{title_suffix} ({self.wind_var})', fontsize=12, fontweight='bold')
        
        self.map_fig.tight_layout()
        
        # Rebind events after axis recreation
        self.map_canvas.mpl_connect('button_press_event', self.on_map_click)
        self.map_canvas.mpl_connect('motion_notify_event', self.on_map_hover)
        self.map_canvas.mpl_connect('scroll_event', self.on_map_scroll)
        
        self.map_canvas.draw()
        
    def on_map_scroll(self, event):
        """Handle mouse wheel scroll for zooming"""
        if event.inaxes != self.map_ax:
            return
            
        if self.wind_data is None:
            return
        
        # Get current axis limits
        x_min, x_max = self.map_ax.get_xlim()
        y_min, y_max = self.map_ax.get_ylim()
        
        # Get mouse position
        x_data = event.xdata
        y_data = event.ydata
        
        if x_data is None or y_data is None:
            return
        
        # Zoom factor
        zoom_factor = 0.9 if event.button == 'up' else 1.1
        
        # Calculate new limits centered on mouse position
        x_range = (x_max - x_min) * zoom_factor
        y_range = (y_max - y_min) * zoom_factor
        
        # Calculate position of mouse in the current view (0 to 1)
        x_ratio = (x_data - x_min) / (x_max - x_min)
        y_ratio = (y_data - y_min) / (y_max - y_min)
        
        # Set new limits
        new_x_min = x_data - x_range * x_ratio
        new_x_max = x_data + x_range * (1 - x_ratio)
        new_y_min = y_data - y_range * y_ratio
        new_y_max = y_data + y_range * (1 - y_ratio)
        
        self.map_ax.set_xlim(new_x_min, new_x_max)
        self.map_ax.set_ylim(new_y_min, new_y_max)
        
        self.map_canvas.draw_idle()
        
    def on_map_click(self, event):
        """Handle click event on the map"""
        if event.inaxes != self.map_ax:
            return
            
        if self.wind_data is None:
            return
            
        # Get click coordinates
        x_click = event.xdata
        y_click = event.ydata
        
        if x_click is None or y_click is None:
            return
            
        # Select nearest point
        try:
            self.selected_point = self.wind_data.sel(
                {self.x_name: x_click, self.y_name: y_click}, 
                method="nearest"
            )
            
            # Get actual coordinates of selected point
            actual_x = float(self.selected_point[self.x_name].values)
            actual_y = float(self.selected_point[self.y_name].values)
            
            # Calculate cell boundaries for red square
            lons = self.wind_mean[self.x_name].values
            lats = self.wind_mean[self.y_name].values
            
            # Find cell size (spacing between grid points)
            if len(lons) > 1:
                dx = float(np.abs(lons[1] - lons[0]))
            else:
                dx = 0.1
            if len(lats) > 1:
                dy = float(np.abs(lats[1] - lats[0]))
            else:
                dy = 0.1
            
            # Remove previous selection patch if it exists
            if self.selection_patch is not None:
                try:
                    self.selection_patch.remove()
                except:
                    pass
            
            # Draw red square around selected cell
            self.selection_patch = Rectangle(
                (actual_x - dx/2, actual_y - dy/2), dx, dy,
                linewidth=2, edgecolor='red', facecolor='none',
                transform=ccrs.PlateCarree(), zorder=10
            )
            self.map_ax.add_patch(self.selection_patch)
            self.map_canvas.draw()
            
            # Update coordinate display
            self.coord_label.config(
                text=f"Selected: ({actual_x:.3f}, {actual_y:.3f})"
            )
            
            # Plot time series
            self.plot_time_series(actual_x, actual_y)
            
        except Exception as e:
            print(f"Error selecting point: {e}")
    
    def on_map_hover(self, event):
        """Handle hover event on the map to show wind speed"""
        if event.inaxes != self.map_ax:
            # Remove annotation and hover rectangle if mouse leaves the map
            if self.hover_annotation is not None:
                try:
                    self.hover_annotation.remove()
                except:
                    pass
                self.hover_annotation = None
            if self.hover_patch is not None:
                try:
                    self.hover_patch.remove()
                except:
                    pass
                self.hover_patch = None
            if self.wind_mean is not None:
                # Update coordinate display - keep selected info
                if self.selected_point is not None:
                    sel_x = float(self.selected_point[self.x_name].values)
                    sel_y = float(self.selected_point[self.y_name].values)
                    self.coord_label.config(text=f"Selected: ({sel_x:.3f}, {sel_y:.3f})")
                else:
                    self.coord_label.config(text="Selected: --")
            self.map_canvas.draw_idle()
            return
            
        if self.wind_mean is None:
            return
            
        # Get hover coordinates
        x_hover = event.xdata
        y_hover = event.ydata
        
        if x_hover is None or y_hover is None:
            return
        
        try:
            # Get data based on view mode
            if self.view_mode.get() == "Mean":
                data_for_hover = self.wind_mean
            else:
                # Single timestep mode
                timestep_idx = self.current_timestep.get() - 1
                data_for_hover = self.wind_data.isel(time=timestep_idx)
            
            # Select nearest point to get wind speed value
            hover_point = data_for_hover.sel(
                {self.x_name: x_hover, self.y_name: y_hover}, 
                method="nearest"
            )
            
            # Get actual cell coordinates
            actual_hover_x = float(hover_point[self.x_name].values)
            actual_hover_y = float(hover_point[self.y_name].values)
            
            wind_speed = float(hover_point.values)
            
            # Calculate cell boundaries for blue hover square
            lons = self.wind_mean[self.x_name].values
            lats = self.wind_mean[self.y_name].values
            
            # Find cell size (spacing between grid points)
            if len(lons) > 1:
                dx = float(np.abs(lons[1] - lons[0]))
            else:
                dx = 0.1
            if len(lats) > 1:
                dy = float(np.abs(lats[1] - lats[0]))
            else:
                dy = 0.1
            
            # Remove old hover patch
            if self.hover_patch is not None:
                try:
                    self.hover_patch.remove()
                except:
                    pass
            
            # Draw blue square around hovered cell
            self.hover_patch = Rectangle(
                (actual_hover_x - dx/2, actual_hover_y - dy/2), dx, dy,
                linewidth=1, edgecolor='blue', facecolor='none',
                transform=ccrs.PlateCarree(), zorder=9
            )
            self.map_ax.add_patch(self.hover_patch)
            
            # Remove old annotation
            if self.hover_annotation is not None:
                try:
                    self.hover_annotation.remove()
                except:
                    pass
            
            # Create new annotation
            self.hover_annotation = self.map_ax.annotate(
                f'{wind_speed:.2f} m/s',
                xy=(x_hover, y_hover),
                xytext=(10, 10),
                textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.8),
                fontsize=9,
                zorder=100
            )
            
            self.map_canvas.draw_idle()
            
        except Exception as e:
            pass  # Silently ignore hover errors
            
    def plot_time_series(self, x, y):
        """Plot time series for selected point, using selected timestep range"""
        self.plot_time_series_selected(x, y)

    def plot_time_series_selected(self, x=None, y=None):
        """Plot time series for selected point and timestep range"""
        self.ts_ax.clear()
        self.ts_ax.axis('on')

        # Use current selected point if not provided
        if x is None or y is None:
            if self.selected_point is None:
                self.ts_canvas.draw()
                return
            x = float(self.selected_point[self.x_name].values)
            y = float(self.selected_point[self.y_name].values)

        # Get time series data
        time = self.selected_point['time'].values
        values = self.selected_point.values

        # Get timestep range (1-based, inclusive)
        first_idx = max(0, self.ts_first_timestep.get() - 1)
        last_idx = min(len(time), self.ts_last_timestep.get())
        time = time[first_idx:last_idx]
        values = values[first_idx:last_idx]

        # Calculate mean
        mean_val = float(np.nanmean(values)) if len(values) > 0 else float('nan')

        # Plot time series
        self.ts_ax.plot(time, values, 'b-', linewidth=1.5)

        # Plot mean line
        if len(values) > 0:
            self.ts_ax.axhline(y=mean_val, color='red', linestyle='--', linewidth=2)

        # Add text annotation
        if len(values) > 0:
            self.ts_ax.text(0.02, 0.98, f'Mean wind speed = {mean_val:.2f} m/s',
                           transform=self.ts_ax.transAxes,
                           verticalalignment='top',
                           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                           fontsize=10, color='red')

        # Formatting
        self.ts_ax.set_xlabel('Time', fontsize=10)
        self.ts_ax.set_ylabel(f'{self.wind_var} (m/s)', fontsize=10)
        self.ts_ax.set_title(f'Time Series at ({x:.2f}°, {y:.2f}°)', 
                           fontsize=11, fontweight='bold')
        self.ts_ax.grid(True, alpha=0.3)

        # Rotate x-axis labels for better readability
        self.ts_fig.autofmt_xdate()

        self.ts_fig.tight_layout()
        self.ts_canvas.draw()


def main():
    """Main entry point"""
    root = TkinterDnD.Tk()
    app = WindMapApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
