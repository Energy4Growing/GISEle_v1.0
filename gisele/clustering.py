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
def poles_clustering_and_cleaning(buildings_filter, crs, chain_upper_bound,pole_upper_bound):
    def create_clusters(buildings_filter,max_distance):
        coordinates = [(point.x, point.y) for point in buildings_filter.geometry]
        kdtree = cKDTree(coordinates)
        assigned = np.zeros(len(buildings_filter.geometry), dtype=bool) 
        #Here it creates a boolean fixed to false 
        clusters = []
        def dfs(node, current_cluster):
            # Depth-first search to find connected points within the given distance
            neighbors = kdtree.query_ball_point(coordinates[node], chain_upper_bound)
            unassigned_neighbors = [neighbor for neighbor in neighbors if not assigned[neighbor]]

            # Mark neighbors as assigned
            assigned[unassigned_neighbors] = True

            # Add the current point to the current cluster if it hasn't been added already
            if node not in current_cluster:
                current_cluster.append(node)

            # Recursively process unassigned neighbors
            for neighbor in unassigned_neighbors:
                dfs(neighbor, current_cluster)

        # Iterate through points to form clusters
        for i, shapely_point in enumerate(buildings_filter.geometry):
            if not assigned[i]:
                current_cluster = []
                dfs(i, current_cluster)
                clusters.append(current_cluster)
        return clusters
    result_clusters = create_clusters(buildings_filter,chain_upper_bound) 
    i=0
    for clus in result_clusters:
        if len(clus)>2: # if there are more thn 2 big macro areas
            coords = [(point.x, point.y) for point in buildings_filter.loc[clus,'geometry']]
            distances = squareform(pdist(coords))
            agg_cluster = AgglomerativeClustering(distance_threshold=pole_upper_bound,n_clusters=None,  linkage='complete')
            cluster_labels = agg_cluster.fit_predict(distances)
            if len(set(cluster_labels))>1: #if agglomerative clustering find more than 1 subgroups
                for j in list(set(cluster_labels)):
                    indices = [index for index, value in enumerate(cluster_labels) if value == j]
                    buildings_filter.loc[[clus[k] for k in indices],'Group2']=i
                    i+=1
                 
            else:
                buildings_filter.loc[clus,'Group2']=i
        else:
            buildings_filter.loc[clus,'Group2']=i
        i+=1 

    collapse_results = [item for sublist in result_clusters for item in sublist]
    for i in range(len(result_clusters)):
        buildings_filter.loc[result_clusters[i],'Group']=i
    buildings_adjusted = []
    area=[]
    num=[] 
    elec_access = []  
    
    cons = [] 
    # pdb.set_trace()
    for group in buildings_filter['Group2'].unique():
        buildings_adjusted.append(MultiPoint(buildings_filter.loc[buildings_filter['Group2']==group,'geometry'].values).centroid)
        area.append(buildings_filter.loc[buildings_filter['Group2']==group,'area'].sum()) 
        cons.append(buildings_filter.loc[buildings_filter['Group2']==group,'cons (kWh/'].sum())
        num.append(len(buildings_filter.loc[buildings_filter['Group2']==group,'area'])) 
        elec_access.append(buildings_filter.loc[buildings_filter['Group2']==group,'elec acces'].mean())
    
    buildings_adjusted_gdf = gpd.GeoDataFrame({'area':area,'number':num, 'cons (kWh/':cons, 'elec acces':elec_access},geometry=buildings_adjusted,crs=crs)
    
    return buildings_adjusted_gdf


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



