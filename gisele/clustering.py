import numpy as np
import os 

import geopandas as gpd  

from scipy.spatial import cKDTree 
from scipy.spatial.distance import pdist, squareform   
from scipy.interpolate import interp1d 
from scipy.ndimage import convolve
from sklearn.cluster import AgglomerativeClustering 
from shapely.geometry import Point, MultiPoint, Polygon, MultiPolygon

from shapely.ops import unary_union
from osgeo import gdal

import rasterio
from rasterio.mask import mask



def building_to_cluster_v1(crs,case_study, study_area_gpd, country, urbanity, area_lower_bound, max_distance_pole, pole_distance, radius, dens_filter):   
    gisele_folder=os.getcwd()
    database =os.path.join(gisele_folder,'Database')
    study_area_buffered=study_area_gpd
    building_path = os.path.join(database,country,'Households','Households.gpkg')
    buildings_df_original = gpd.read_file(building_path) 
    if urbanity == True: 
          
        buildings_df_original.rename(columns={'area_in_me': 'area'}, inplace=True)

        buildings_df = buildings_df_original.to_crs(crs)  

        buildings_df['area'] = buildings_df.area 

        buildings_df['geometry'] = buildings_df.geometry.centroid   
        buildings_df=gpd.clip(buildings_df,study_area_buffered) 
        buildings_df = buildings_df.reset_index(drop=True)  
        
        
        buildings_df = buildings_df[buildings_df['area']>area_lower_bound]
        buildings_df['ID']=[*range(len(buildings_df))]
        buildings_df.reset_index(inplace=True,drop=True)
        buildings_df_up = poles_clustering_and_cleaning(buildings_df, crs, max_distance_pole, pole_distance)
        
        urbanity_raster = os.path.join(database, country, 'Urbanity', 'Urbanity.tif')
        output_modified_raster = os.path.join(database,country, "Urbanity", "Urbanity_clip_rep_convolve.tif")
        if not os.path.exists(output_modified_raster):
            with rasterio.open(urbanity_raster) as src:
                # Convert study area to list of GeoJSON geometries in raster CRS
                study_area_geom = [feature["geometry"] for feature in study_area_buffered.to_crs(src.crs).__geo_interface__['features']]
                
                # Clip raster
                out_image, out_transform = mask(src, study_area_geom, crop=True)
                
                # Copy metadata and update
                out_meta = src.meta.copy()
                out_meta.update({
                    "driver": "GTiff",
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform
                })
            with rasterio.open(os.path.join(database,country, "Urbanity", "Urbanity_clip.tif"), "w", **out_meta) as dest:
                dest.write(out_image)

            input_raster = gdal.Open(os.path.join(database,country, "Urbanity", "Urbanity_clip.tif"))
            output_raster =  os.path.join(database,country, "Urbanity", "Urbanity_clip_rep.tif")
            warp = gdal.Warp(output_raster, input_raster, dstSRS=crs)
            
            
            Urbanity = rasterio.open(output_raster) 
            
            raster = Urbanity.read(1)
            
            # Define the convolution kernel (3x3 kernel with all values set to 1)
            kernel = np.ones((3, 3))
            
            neighbor_sum = convolve(raster, kernel,  mode='nearest')


            result = raster + 0.5 * (neighbor_sum - raster)
            result = result.astype(np.float32)
            # Update metadata for the output file
            meta = Urbanity.meta.copy()

            with rasterio.open(output_modified_raster, "w", **meta) as dest:
                dest.write(result, 1)  


        Urbanity_final = rasterio.open(output_modified_raster) 
        coords = [(point.x, point.y) for point in buildings_df_up['geometry']]
        buildings_df_up['urbanity'] = [x[0] for x in Urbanity_final.sample(coords)] 
        

        
    
    else: 
        print('Skipped')
        #TODO Completare qui 
        
        
    buildings_df_up = buildings_df_up.reset_index(drop=True)    
    x_interp = [55,150]
    y_interp = [radius,40]
    
    # Create the interpolator function
    interpolator = interp1d(x_interp, y_interp, kind='linear', fill_value='extrapolate')
    for index, row in buildings_df_up.iterrows():
        point_geometry = row.geometry 
        urbanity_value = row['urbanity'] 
        buffer_radius = interpolator(urbanity_value)

        buildings_df_up.at[index, 'buffer'] = point_geometry.buffer(buffer_radius)
        
    geometries = buildings_df_up['buffer'].tolist()
    clusters_MP = unary_union(geometries)

    clusters = list(clusters_MP.geoms) if isinstance(clusters_MP, MultiPolygon) else [clusters_MP]

    
    clusters_gdf = gpd.GeoDataFrame(geometry=clusters, crs=crs) 
    clusters_gdf = clusters_gdf.reset_index().rename(columns={'index': 'cluster_ID'})
    clusters_gdf['cluster_ID'] = clusters_gdf['cluster_ID']+1 
    spatial_join = gpd.sjoin(buildings_df_up, clusters_gdf, how='left', predicate='within') 
    
    try: 
        buildings_df_up['cluster_ID'] = spatial_join['cluster_ID']   
    except: 
        buildings_df_up['cluster_ID'] = spatial_join['cluster_ID_right']  
    
    cluster_counts = buildings_df_up['cluster_ID'].value_counts() 
    clusters_to_keep = cluster_counts[cluster_counts >= dens_filter].index 
    clusters_gdf = clusters_gdf[clusters_gdf['cluster_ID'].isin(clusters_to_keep)]
    
    buildings_df_up.loc[~buildings_df_up['cluster_ID'].isin(clusters_to_keep), 'cluster_ID'] = -1
    
     
    average_elec_access = buildings_df_up.groupby('cluster_ID')['elec acces'].mean()   
    #I do here a average electrification access and then for each clustrer I do a random selection of the electrification according to that percentage
    threshold = 0.3
  
    if len(clusters_gdf) > 0:
        clusters_gdf = clusters_gdf.merge(average_elec_access, left_on='cluster_ID', right_index=True, how='left')  
        clusters_gdf.drop(columns=['cluster_ID'], inplace=True)
        clusters_gdf['elec acces'] = clusters_gdf['elec acces']/100
        clusters_gdf = clusters_gdf[clusters_gdf['elec acces'] < threshold].reset_index()
        clusters_gdf.drop(columns=['index'], inplace=True)
        clusters_gdf['cluster_ID'] = clusters_gdf.index +1
    
    clusters_gdf = clusters_gdf.reset_index().rename(columns={'index': 'cluster_ID'}) 
    clusters_gdf['cluster_ID'] = clusters_gdf.index + 1 
    clusters_gdf = clusters_gdf.loc[:, ~clusters_gdf.columns.duplicated()]


    
    output_path_clusters = os.path.join(gisele_folder,'Case studies',case_study,'Input','Communities_boundaries')

    clusters_gdf.to_file(output_path_clusters)  

    return clusters_gdf



