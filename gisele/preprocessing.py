

import os
import pandas as pd
import geopandas as gpd

def create_folder(case_study, country,crs):
    gisele_folder=os.getcwd()
    database =os.path.join(gisele_folder,'Database')
    cluster_folder = os.path.join(database,country,'Clusters','Communities.shp')
    substations_folder = os.path.join(database,country,'Substations','con_points.shp')
    study_area_folder = os.path.join(database,country,'Study_area','Study_area.shp')

    if not os.path.exists(os.path.join(gisele_folder,'Case studies',case_study)): # if this is a new project, create the starting point for the analysis
        # Create new folders for the study case
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Input'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Output'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Communities'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Microgrid'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Optimization'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Geospatial_Data'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Optimization','MILP_output'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Output','MILP_processed'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Optimization','all_data'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Optimization','MILP_input'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Optimization','all_data','Lines_connections'))
        os.makedirs(os.path.join(gisele_folder,'Case studies',case_study,'Intermediate','Optimization','all_data','Lines_marked'))
        # Copy the Configuration file from the general input
        pd.read_csv((os.path.join(gisele_folder,'general_input','Configuration.csv'))).to_csv(os.path.join(gisele_folder,'Case studies',case_study,'Input','Configuration.csv'))
        
        # Read the possible connection points and write them in the case study's folder
        Substations = gpd.read_file(substations_folder)
        Substations_crs = Substations.to_crs(crs)

        Substations['X'] = [Substations_crs['geometry'].values[i].xy[0][0] for i in range(Substations.shape[0])]
        Substations['Y'] = [Substations_crs['geometry'].values[i].xy[1][0] for i in range(Substations.shape[0])]
        Substations.to_file(os.path.join(gisele_folder,'Case studies', case_study, 'Input', 'substations'))
        # Read the polygon of the study area and write it in the local database.
        study_area = gpd.read_file(study_area_folder)
        study_area.to_file(os.path.join(gisele_folder,'Case studies',case_study,'Input','Study_area'))
        # Read the communities and write them in the local database
        Clusters = gpd.read_file(cluster_folder)
        Clusters = Clusters.to_crs(crs)
        Clusters['cluster_ID'] = [*range(1, Clusters.shape[0] + 1)]
        for i, row in Clusters.iterrows(): # this is just in case one of the polygons is saved as a MP with just 1 polygon
            if row['geometry'].geom_type == 'MultiPolygon':
                Clusters.loc[i, 'geometry'] = row['geometry'][0]
        Clusters.to_file(os.path.join(gisele_folder,'Case studies',case_study,'Input','Communities_boundaries'))
    else: # not a new project, just read the files from the local folder
        Clusters = gpd.read_file(os.path.join(gisele_folder,'Case studies',case_study,'Input','Communities_boundaries','Communities_boundaries.shp'))
        study_area = gpd.read_file(os.path.join(gisele_folder,'Case studies',case_study,'Input','Study_area','Study_area.shp'))
        Substations = gpd.read_file(os.path.join(gisele_folder,'Case studies',case_study,'Input','substations','substations.shp'))
    
    
    return Clusters, study_area, Substations